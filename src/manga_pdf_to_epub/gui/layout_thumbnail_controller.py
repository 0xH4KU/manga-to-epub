from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path

from ..fitz_compat import load_fitz
from .layout_preview import ThumbnailCache, normalize_preview_size


fitz = load_fitz()


class EpubLayoutThumbnailMixin:
    def _thumbnail_for_page(self, page_index: int, max_w: int, max_h: int) -> tk.PhotoImage | None:
        if self.pdf_path is None:
            return None
        bucket_w, bucket_h = normalize_preview_size(max_w, max_h)
        cache_key = ("pdf", page_index, bucket_w, bucket_h)
        cached = self.thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached
        if hasattr(self, "_thumbnail_render_jobs"):
            self._start_thumbnail_render(page_index, max_w, max_h, cache_key)
            return None
        try:
            doc = self._pdf_document()
            page = doc[page_index - 1]
            zoom = min(max_w / page.rect.width, max_h / page.rect.height)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = tk.PhotoImage(data=pix.tobytes("png"))
            self.thumbnail_cache[cache_key] = image
            return image
        except Exception:
            if hasattr(self, "status"):
                self.status.set(f"Preview failed for page {page_index}.")
            return None

    def _source_uses_pdf_renderer(self) -> bool:
        return self.pdf_path is not None and self.pdf_path.suffix.lower() == ".pdf"

    def _start_thumbnail_render(self, page_index: int, max_w: int, max_h: int, cache_key: tuple) -> None:
        if self.pdf_path is None or cache_key in self._thumbnail_render_jobs:
            return
        pdf_path = self.pdf_path
        generation = self._thumbnail_cache_generation
        self._thumbnail_render_jobs.add(cache_key)

        def worker() -> None:
            try:
                png_data = self._render_pdf_thumbnail_bytes(pdf_path, page_index, max_w, max_h)
                self.root.after(0, lambda: self._thumbnail_render_done(cache_key, pdf_path, generation, png_data, None))
            except Exception as exc:
                self.root.after(0, lambda exc=exc: self._thumbnail_render_done(cache_key, pdf_path, generation, None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _render_pdf_thumbnail_bytes(self, pdf_path: Path, page_index: int, max_w: int, max_h: int) -> bytes:
        with fitz.open(pdf_path) as doc:
            page = doc[page_index - 1]
            zoom = min(max_w / page.rect.width, max_h / page.rect.height)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            return pix.tobytes("png")

    def _thumbnail_render_done(
        self,
        cache_key: tuple,
        pdf_path: Path,
        generation: int,
        png_data: bytes | None,
        exc: Exception | None,
    ) -> None:
        self._thumbnail_render_jobs.discard(cache_key)
        if self.pdf_path != pdf_path or generation != self._thumbnail_cache_generation:
            return
        if exc is not None or png_data is None:
            if hasattr(self, "status"):
                self.status.set("Preview thumbnail render failed.")
            return
        try:
            self.thumbnail_cache[cache_key] = tk.PhotoImage(data=png_data)
            if hasattr(self, "refresh_preview_views"):
                self.refresh_preview_views()
            else:
                self.refresh_preview()
        except Exception:
            if hasattr(self, "status"):
                self.status.set("Preview thumbnail render failed.")

    def _pdf_document(self):
        if self.pdf_path is None:
            return None
        if getattr(self, "_pdf_doc", None) is not None and self._pdf_doc_path == self.pdf_path:
            return self._pdf_doc
        self._close_pdf_document()
        self._pdf_doc = fitz.open(self.pdf_path)
        self._pdf_doc_path = self.pdf_path
        return self._pdf_doc

    def _close_pdf_document(self) -> None:
        doc = getattr(self, "_pdf_doc", None)
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
        self._pdf_doc = None
        self._pdf_doc_path = None

    def _reset_preview_cache(self) -> None:
        if not isinstance(getattr(self, "thumbnail_cache", None), ThumbnailCache):
            self.thumbnail_cache = ThumbnailCache()
        else:
            self.thumbnail_cache.clear()
        if hasattr(self, "_thumbnail_render_jobs"):
            self._thumbnail_render_jobs.clear()
        self._thumbnail_cache_generation = getattr(self, "_thumbnail_cache_generation", 0) + 1
        self._close_pdf_document()
