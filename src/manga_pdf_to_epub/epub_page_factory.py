from __future__ import annotations

from .epub_writer import EpubPage, media_type_for_ext
from .pdf_image_types import ImageStream
from .pdf_png import image_to_epub_member


def page_from_image(image: ImageStream, padding: int) -> tuple[EpubPage, str]:
    ext, payload = image_to_epub_member(image)
    page_number = f"{image.index:0{padding}d}"
    return (
        EpubPage(
            index=image.index,
            width=image.width,
            height=image.height,
            image_href=f"images/page-{page_number}.{ext}",
            image_media_type=media_type_for_ext(ext),
            image_data=payload,
            xhtml_href=f"xhtml/page-{page_number}.xhtml",
            item_id=f"page-{image.index:04d}",
            label=f"Page {image.index}",
        ),
        ext,
    )
