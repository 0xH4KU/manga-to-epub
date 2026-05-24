from __future__ import annotations

import tkinter as tk
from io import BytesIO

from .layout_preview import (
    preview_entries,
    preview_index_for_selection,
    spread_slots,
    thumbnail_cache_key,
)
from .layout_support import VirtualBlank


class EpubLayoutPreviewMixin:
    def refresh_preview(self) -> None:
        self._refresh_preview_canvas(self.preview, self.photo_refs, self.selected_index())

    def _refresh_preview_canvas(self, canvas, photo_refs: list, selected: int | None) -> None:
        canvas.delete("all")
        photo_refs.clear()
        if self.model is None or not self.model.entries:
            return
        if selected is None:
            selected = 0
        preview_entries = self._preview_entries()
        preview_selected = self._preview_index_for_selection(selected)
        pair_start = preview_selected if preview_selected % 2 == 0 else preview_selected - 1
        entries = preview_entries[pair_start : pair_start + 2]

        width = max(400, canvas.winfo_width())
        height = max(300, canvas.winfo_height())
        gap = 12
        page_w = (width - gap * 3) // 2
        page_h = height - gap * 2

        slots = self._spread_slots(pair_start, gap, page_w)
        for entry, (x, y) in zip(entries, slots):
            self._draw_entry_on_canvas(canvas, photo_refs, entry, x, y, page_w, page_h)

    def _preview_index_for_selection(self, selected: int) -> int:
        return preview_index_for_selection(selected, self._uses_apple_cover_gap())

    def _spread_slots(self, pair_start: int, gap: int, page_w: int) -> list[tuple[int, int]]:
        return spread_slots(pair_start, gap, page_w, self._uses_apple_cover_gap())

    def _preview_entries(self):
        if self.model is None:
            return []
        return preview_entries(list(self.model.entries), self._uses_apple_cover_gap())

    def _uses_apple_cover_gap(self) -> bool:
        if self.model is None or not self.model.entries:
            return False
        return self.apple_preview.get()

    def _draw_entry_on_canvas(self, canvas, photo_refs: list, entry, x: int, y: int, max_w: int, max_h: int) -> None:
        canvas.create_rectangle(x, y, x + max_w, y + max_h, fill="#ffffff", outline="#707070")
        if entry.is_blank:
            fill = "#a0a0a0" if isinstance(entry, VirtualBlank) else "#606060"
            canvas.create_text(x + max_w // 2, y + max_h // 2, text=entry.label, fill=fill)
            return
        if getattr(entry, "source_index", None) is None:
            photo = self._thumbnail_for_entry(entry, max_w, max_h)
        elif self._source_uses_pdf_renderer():
            photo = self._thumbnail_for_page(entry.page.index, max_w, max_h)
        else:
            photo = self._thumbnail_for_source_entry(entry, max_w, max_h)
        if photo is None:
            canvas.create_text(x + max_w // 2, y + max_h // 2, text=entry.label, fill="#202020")
            return
        photo_refs.append(photo)
        image_x = x + (max_w - photo.width()) // 2
        image_y = y + (max_h - photo.height()) // 2
        canvas.create_image(image_x, image_y, anchor=tk.NW, image=photo)
        canvas.create_text(x + 8, y + 16, text=entry.label, anchor=tk.W, fill="#ffffff")

    def _draw_entry(self, entry, x: int, y: int, max_w: int, max_h: int) -> None:
        self._draw_entry_on_canvas(self.preview, self.photo_refs, entry, x, y, max_w, max_h)

    def _thumbnail_for_source_entry(self, entry, max_w: int, max_h: int) -> tk.PhotoImage | None:
        return self._thumbnail_for_entry(entry, max_w, max_h)

    def _thumbnail_for_entry(self, entry, max_w: int, max_h: int) -> tk.PhotoImage | None:
        cache_key = self._thumbnail_cache_key(entry, max_w, max_h)
        cached = self.thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            image_data = entry.page.load_image_data()
            if _is_png_payload(image_data):
                image = tk.PhotoImage(data=image_data)
            else:
                image = tk.PhotoImage(data=_preview_png_thumbnail(image_data, max_w, max_h))
            scale = max(1, int(max(image.width() / max_w, image.height() / max_h, 1)))
            if scale > 1:
                image = image.subsample(scale, scale)
            self.thumbnail_cache[cache_key] = image
            return image
        except Exception:
            return None

    def _thumbnail_cache_key(self, entry, max_w: int, max_h: int):
        return thumbnail_cache_key(entry, max_w, max_h)


def _is_png_payload(payload: bytes) -> bool:
    return payload.startswith(b"\x89PNG\r\n\x1a\n")


def _preview_png_thumbnail(payload: bytes, max_w: int, max_h: int) -> bytes:
    from PIL import Image, ImageOps

    with Image.open(BytesIO(payload)) as image:
        frame = ImageOps.exif_transpose(image)
        if frame.mode not in {"RGB", "RGBA"}:
            has_alpha = "A" in frame.getbands() or (frame.mode == "P" and "transparency" in frame.info)
            frame = frame.convert("RGBA" if has_alpha else "RGB")
        frame.thumbnail((max(1, max_w), max(1, max_h)), Image.Resampling.LANCZOS)
        output = BytesIO()
        frame.save(output, format="PNG")
        return output.getvalue()
