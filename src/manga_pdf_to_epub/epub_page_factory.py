from __future__ import annotations

from .epub_writer import EpubPage, media_type_for_ext
from .pdf_image_types import ImageStream
from .pdf_png import image_to_epub_member


def page_from_image(image: ImageStream, padding: int, load_payload: bool = True) -> tuple[EpubPage, str]:
    ext = _epub_member_ext(image)
    payload = image_to_epub_member(image)[1] if load_payload else None
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
            image_data_loader=None if load_payload else lambda image=image: image_to_epub_member(image)[1],
        ),
        ext,
    )


def _epub_member_ext(image: ImageStream) -> str:
    if image.filter_name in {"PNG", "FlateDecode"}:
        return "png"
    if image.filter_name == "DCTDecode":
        return "jpg"
    return image_to_epub_member(image)[0]
