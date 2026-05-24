from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Callable

from .pdf_image_types import ImageStream, PdfImageError


def images_in_pdf_page_order(pdf_path: Path, load_payloads: bool = True) -> list[ImageStream]:
    fitz = _load_fitz()
    if fitz is None:
        raise PdfImageError("PyMuPDF is required for PDF page-order image extraction. Install PyMuPDF and try again.")

    with fitz.open(pdf_path) as doc:
        images: list[ImageStream] = []
        for page in doc:
            page_images = page.get_images(full=True)
            for page_image in page_images:
                xref = page_image[0]
                image = _image_from_xref(doc, xref, len(images) + 1, load_payloads=load_payloads, pdf_path=pdf_path)
                if image is not None:
                    images.append(image)

    return images


def _load_fitz():
    try:
        return importlib.import_module("fitz")
    except ModuleNotFoundError:
        return None


def _image_from_xref(
    doc,
    xref: int,
    index: int,
    load_payloads: bool = True,
    pdf_path: Path | None = None,
) -> ImageStream | None:
    subtype = doc.xref_get_key(xref, "Subtype")
    if subtype[1] != "/Image":
        return None

    filter_type, filter_value = doc.xref_get_key(xref, "Filter")
    if filter_type == "name":
        filter_name = filter_value.removeprefix("/")
    else:
        extracted = doc.extract_image(xref)
        ext = extracted["ext"]
        if ext == "jpeg":
            filter_name = "DCTDecode"
        elif ext == "png":
            payload = _payload_or_loader(
                load_payloads,
                lambda: extracted["image"],
                _lazy_extracted_image_loader(pdf_path, xref),
            )
            return ImageStream(
                index=index,
                width=extracted["width"],
                height=extracted["height"],
                bits_per_component=8,
                color_space=b"/DeviceRGB",
                filter_name="PNG",
                decode_parms=None,
                data=payload[0],
                xref=xref,
                data_loader=payload[1],
            )
        else:
            raise PdfImageError(f"Unsupported extracted image extension for xref {xref}: {ext}")

    if filter_name == "DCTDecode":
        payload = _payload_or_loader(load_payloads, lambda: doc.xref_stream_raw(xref), _lazy_raw_stream_loader(pdf_path, xref))
        return ImageStream(
            index=index,
            width=_xref_required_int(doc, xref, "Width"),
            height=_xref_required_int(doc, xref, "Height"),
            bits_per_component=_xref_required_int(doc, xref, "BitsPerComponent"),
            color_space=_xref_object(doc, xref, "ColorSpace"),
            filter_name=filter_name,
            decode_parms=_xref_object(doc, xref, "DecodeParms"),
            data=payload[0],
            xref=xref,
            data_loader=payload[1],
        )

    if filter_name == "FlateDecode":
        payload = _payload_or_loader(load_payloads, lambda: doc.xref_stream_raw(xref), _lazy_raw_stream_loader(pdf_path, xref))
        return ImageStream(
            index=index,
            width=_xref_required_int(doc, xref, "Width"),
            height=_xref_required_int(doc, xref, "Height"),
            bits_per_component=_xref_required_int(doc, xref, "BitsPerComponent"),
            color_space=_normalize_xref_color_space(doc, _xref_object(doc, xref, "ColorSpace")),
            filter_name=filter_name,
            decode_parms=_normalize_pdf_object(_xref_object(doc, xref, "DecodeParms")),
            data=payload[0],
            xref=xref,
            data_loader=payload[1],
        )

    if filter_name in {"JBIG2Decode"}:
        return _decoded_image_from_xref(doc, xref, index, load_payloads=load_payloads, pdf_path=pdf_path)

    raise PdfImageError(f"Unsupported image filter for xref {xref}: {filter_name}")


def _decoded_image_from_xref(
    doc,
    xref: int,
    index: int,
    load_payloads: bool = True,
    pdf_path: Path | None = None,
) -> ImageStream:
    extracted = doc.extract_image(xref)
    ext = extracted["ext"]
    if ext != "png":
        raise PdfImageError(f"Unsupported extracted image extension for xref {xref}: {ext}")
    payload = _payload_or_loader(load_payloads, lambda: extracted["image"], _lazy_extracted_image_loader(pdf_path, xref))
    return ImageStream(
        index=index,
        width=extracted["width"],
        height=extracted["height"],
        bits_per_component=8,
        color_space=b"/DeviceRGB",
        filter_name="PNG",
        decode_parms=None,
        data=payload[0],
        xref=xref,
        data_loader=payload[1],
    )


def _payload_or_loader(
    load_payloads: bool,
    load_data: Callable[[], bytes],
    loader: Callable[[], bytes] | None,
) -> tuple[bytes | None, Callable[[], bytes] | None]:
    if load_payloads or loader is None:
        return load_data(), None
    return None, loader


def _lazy_raw_stream_loader(pdf_path: Path | None, xref: int) -> Callable[[], bytes] | None:
    if pdf_path is None:
        return None

    def load() -> bytes:
        fitz = _load_fitz()
        if fitz is None:
            raise PdfImageError("PyMuPDF is required for PDF image extraction. Install PyMuPDF and try again.")
        with fitz.open(pdf_path) as doc:
            return doc.xref_stream_raw(xref)

    return load


def _lazy_extracted_image_loader(pdf_path: Path | None, xref: int) -> Callable[[], bytes] | None:
    if pdf_path is None:
        return None

    def load() -> bytes:
        fitz = _load_fitz()
        if fitz is None:
            raise PdfImageError("PyMuPDF is required for PDF image extraction. Install PyMuPDF and try again.")
        with fitz.open(pdf_path) as doc:
            return doc.extract_image(xref)["image"]

    return load


def _xref_required_int(doc, xref: int, key: str) -> int:
    kind, value = doc.xref_get_key(xref, key)
    if kind != "int":
        raise PdfImageError(f"xref {xref} image dictionary missing /{key}")
    return int(value)


def _xref_object(doc, xref: int, key: str) -> bytes | None:
    kind, value = doc.xref_get_key(xref, key)
    if kind == "null":
        return None
    return value.encode("latin1")


def _normalize_pdf_object(obj: bytes | None) -> bytes | None:
    if obj is None:
        return None
    return obj.strip()


def _normalize_xref_color_space(doc, color_space: bytes | None) -> bytes | None:
    color_space = _normalize_pdf_object(color_space)
    if color_space is None:
        return None
    match = re.match(rb"\[\s*/Indexed\s*/DeviceRGB\s+(\d+)\s+(\d+)\s+(\d+)\s+R\s*\]", color_space)
    if not match:
        return color_space
    highest_index = int(match.group(1))
    palette_xref = int(match.group(2))
    generation = int(match.group(3))
    if generation != 0:
        return color_space
    expected = (highest_index + 1) * 3
    palette = doc.xref_stream(palette_xref)
    if not palette or len(palette) < expected:
        return color_space
    return b"[/Indexed /DeviceRGB " + str(highest_index).encode("ascii") + b" <" + palette[:expected].hex().encode("ascii") + b">]"
