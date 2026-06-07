from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image


def render_pdf_thumbnails(
    pdf_path: Path,
    thumbs_dir: Path,
    *,
    height: int = 900,
    jpeg_quality: int = 84,
) -> list[Path]:
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc, start=1):
            zoom = height / page.rect.height
            matrix = fitz.Matrix(zoom, zoom)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            path = thumbs_dir / f"page-{page_index:04d}.jpg"
            image.save(path, "JPEG", quality=jpeg_quality, optimize=True)
            rendered.append(path)
    return rendered


def load_thumbnail(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")
