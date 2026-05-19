#!/usr/bin/env python3
"""Losslessly extract image streams from simple comic PDFs into CBZ archives."""

from __future__ import annotations

import argparse
import binascii
import importlib
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo


class PdfImageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImageStream:
    index: int
    width: int
    height: int
    bits_per_component: int
    color_space: bytes | None
    filter_name: str
    decode_parms: bytes | None
    data: bytes
    xref: int | None = None


def _find_dict_bounds(data: bytes, stream_pos: int) -> tuple[int, int] | None:
    window_start = max(0, stream_pos - 8192)
    window = data[window_start:stream_pos]
    matches = list(re.finditer(rb"\b\d+\s+\d+\s+obj\s*", window))
    if not matches:
        return None
    dict_start = window_start + matches[-1].end()
    while dict_start < len(data) and data[dict_start] in b" \t\r\n":
        dict_start += 1
    if data[dict_start : dict_start + 2] != b"<<":
        return None
    dict_end = _matching_double_angle(data, dict_start) + 2
    return dict_start, dict_end


def _stream_data_start(data: bytes, stream_pos: int) -> int:
    pos = stream_pos + len(b"stream")
    if data[pos : pos + 2] == b"\r\n":
        return pos + 2
    if data[pos : pos + 1] in (b"\r", b"\n"):
        return pos + 1
    return pos


def _is_stream_token(data: bytes, stream_pos: int) -> bool:
    before = data[stream_pos - 1 : stream_pos] if stream_pos else b""
    after = data[stream_pos + len(b"stream") : stream_pos + len(b"stream") + 1]
    delimiters = b"\x00\t\n\f\r <>[]()/%"
    return (not before or before in delimiters) and (not after or after in delimiters)


def _extract_int(dictionary: bytes, key: bytes) -> int | None:
    match = re.search(rb"/" + re.escape(key) + rb"\s+(\d+)", dictionary)
    return int(match.group(1)) if match else None


def _extract_object(dictionary: bytes, key: bytes) -> bytes | None:
    match = re.search(rb"/" + re.escape(key) + rb"\s*", dictionary)
    if not match:
        return None
    pos = match.end()
    return _read_pdf_object(dictionary, pos)


def _read_pdf_object(data: bytes, pos: int) -> bytes:
    while pos < len(data) and data[pos] in b" \t\r\n":
        pos += 1
    if data[pos : pos + 2] == b"<<":
        return data[pos : _matching_double_angle(data, pos) + 2]
    if data[pos : pos + 1] == b"[":
        return data[pos : _matching_bracket(data, pos) + 1]
    if data[pos : pos + 1] == b"(":
        return data[pos : _matching_paren(data, pos) + 1]
    match = re.match(rb"/[A-Za-z0-9]+|\d+|[^\s<>\[\]()]+", data[pos:])
    if not match:
        raise PdfImageError(f"Cannot parse PDF object near offset {pos}")
    return match.group(0)


def _matching_double_angle(data: bytes, start: int) -> int:
    depth = 0
    pos = start
    while pos < len(data) - 1:
        token = data[pos : pos + 2]
        if token == b"<<":
            depth += 1
            pos += 2
            continue
        if token == b">>":
            depth -= 1
            if depth == 0:
                return pos
            pos += 2
            continue
        if data[pos : pos + 1] == b"(":
            pos = _matching_paren(data, pos) + 1
            continue
        if data[pos : pos + 1] == b"<":
            end = data.find(b">", pos + 1)
            if end < 0:
                raise PdfImageError("Unterminated PDF hex string")
            pos = end + 1
            continue
        pos += 1
    raise PdfImageError("Unterminated PDF dictionary")


def _matching_bracket(data: bytes, start: int) -> int:
    depth = 0
    pos = start
    while pos < len(data):
        char = data[pos : pos + 1]
        if char == b"(":
            pos = _matching_paren(data, pos) + 1
            continue
        if char == b"[":
            depth += 1
        elif char == b"]":
            depth -= 1
            if depth == 0:
                return pos
        pos += 1
    raise PdfImageError("Unterminated PDF array")


def _matching_paren(data: bytes, start: int) -> int:
    depth = 0
    pos = start
    while pos < len(data):
        char = data[pos : pos + 1]
        if char == b"\\":
            pos += 2
            continue
        if char == b"(":
            depth += 1
        elif char == b")":
            depth -= 1
            if depth == 0:
                return pos
        pos += 1
    raise PdfImageError("Unterminated PDF string")


def iter_image_streams(pdf_path: Path) -> list[ImageStream]:
    data = pdf_path.read_bytes()
    images: list[ImageStream] = []
    pos = 0
    while True:
        stream_pos = data.find(b"stream", pos)
        if stream_pos < 0:
            break
        if not _is_stream_token(data, stream_pos):
            pos = stream_pos + len(b"stream")
            continue
        bounds = _find_dict_bounds(data, stream_pos)
        if bounds is None:
            pos = stream_pos + len(b"stream")
            continue
        dict_start, dict_end = bounds
        dictionary = data[dict_start:dict_end]
        length = _extract_int(dictionary, b"Length")
        start = _stream_data_start(data, stream_pos)
        if length is None:
            endstream = data.find(b"endstream", start)
            if endstream < 0:
                raise PdfImageError(f"Missing endstream after offset {stream_pos}")
            raw = data[start:endstream].rstrip(b"\r\n")
            pos = endstream + len(b"endstream")
        else:
            raw = data[start : start + length]
            pos = start + length

        if not re.search(rb"/Subtype\s*/Image", dictionary):
            continue

        filter_name = _extract_filter_name(dictionary)
        width = _extract_required_int(dictionary, b"Width")
        height = _extract_required_int(dictionary, b"Height")
        bpc = _extract_required_int(dictionary, b"BitsPerComponent")
        images.append(
            ImageStream(
                index=len(images) + 1,
                width=width,
                height=height,
                bits_per_component=bpc,
                color_space=_extract_object(dictionary, b"ColorSpace"),
                filter_name=filter_name,
                decode_parms=_extract_object(dictionary, b"DecodeParms"),
                data=raw,
            )
        )
    return images


def _extract_required_int(dictionary: bytes, key: bytes) -> int:
    value = _extract_int(dictionary, key)
    if value is None:
        raise PdfImageError(f"Image dictionary missing /{key.decode('ascii')}")
    return value


def _extract_filter_name(dictionary: bytes) -> str:
    raw_filter = _extract_object(dictionary, b"Filter")
    if raw_filter is None:
        return "none"
    names = re.findall(rb"/([A-Za-z0-9]+)", raw_filter)
    if len(names) != 1:
        raise PdfImageError(f"Unsupported image filter chain: {raw_filter!r}")
    return names[0].decode("ascii")


def image_to_archive_member(image: ImageStream) -> tuple[str, bytes]:
    if image.filter_name == "DCTDecode":
        return "jpg", image.data
    if image.filter_name == "FlateDecode":
        return "png", flate_image_to_png(image)
    raise PdfImageError(f"Unsupported image filter: {image.filter_name}")


def flate_image_to_png(image: ImageStream) -> bytes:
    predictor = _decode_parm_int(image.decode_parms, b"Predictor", 1)
    columns = _decode_parm_int(image.decode_parms, b"Columns", image.width)
    colors = _decode_parm_int(image.decode_parms, b"Colors", _png_channel_count(image.color_space))
    bpc = _decode_parm_int(image.decode_parms, b"BitsPerComponent", image.bits_per_component)

    if columns != image.width:
        raise PdfImageError(f"Unsupported Columns {columns}; expected image width {image.width}")
    if bpc != image.bits_per_component:
        raise PdfImageError(f"DecodeParms BitsPerComponent {bpc} does not match image")

    color_type, palette = _png_color(image.color_space, bpc)
    if 10 <= predictor <= 15:
        return make_png_from_compressed_rows(image.width, image.height, bpc, color_type, image.data, palette)

    raw = zlib.decompress(image.data)
    scanlines = _undo_predictor(raw, predictor, columns, colors, bpc, image.height)
    return make_png_from_scanlines(image.width, image.height, bpc, color_type, scanlines, palette)


def _decode_parm_int(decode_parms: bytes | None, key: bytes, default: int) -> int:
    if decode_parms is None:
        return default
    value = _extract_int(decode_parms, key)
    return value if value is not None else default


def _png_channel_count(color_space: bytes | None) -> int:
    if color_space in (None, b"/DeviceGray"):
        return 1
    if color_space == b"/DeviceRGB":
        return 3
    if color_space.startswith(b"[/Indexed"):
        return 1
    raise PdfImageError(f"Unsupported ColorSpace: {color_space!r}")


def _png_color(color_space: bytes | None, bits_per_component: int) -> tuple[int, bytes | None]:
    if color_space in (None, b"/DeviceGray"):
        return 0, None
    if color_space == b"/DeviceRGB":
        if bits_per_component != 8:
            raise PdfImageError("DeviceRGB PNG output supports 8 bits per component only")
        return 2, None
    if color_space.startswith(b"[/Indexed"):
        return 3, _indexed_palette(color_space)
    raise PdfImageError(f"Unsupported ColorSpace: {color_space!r}")


def _indexed_palette(color_space: bytes) -> bytes:
    match = re.match(rb"\[\s*/Indexed\s*/DeviceRGB\s+(\d+)\s*(.*)\s*\]\s*$", color_space, re.S)
    if not match:
        raise PdfImageError(f"Unsupported indexed ColorSpace: {color_space!r}")
    highest_index = int(match.group(1))
    palette_obj = match.group(2).strip()
    if palette_obj.startswith(b"("):
        palette = _decode_pdf_literal_string(palette_obj)
    elif palette_obj.startswith(b"<") and palette_obj.endswith(b">") and not palette_obj.startswith(b"<<"):
        palette = bytes.fromhex(re.sub(rb"\s+", b"", palette_obj[1:-1]).decode("ascii"))
    else:
        raise PdfImageError(f"Unsupported indexed palette object: {palette_obj!r}")

    expected = (highest_index + 1) * 3
    if len(palette) < expected:
        raise PdfImageError(f"Indexed palette is too short: {len(palette)} < {expected}")
    return palette[:expected]


def _decode_pdf_literal_string(obj: bytes) -> bytes:
    if not (obj.startswith(b"(") and obj.endswith(b")")):
        raise PdfImageError("Not a PDF literal string")
    out = bytearray()
    pos = 1
    end = len(obj) - 1
    escapes = {
        ord("n"): ord("\n"),
        ord("r"): ord("\r"),
        ord("t"): ord("\t"),
        ord("b"): ord("\b"),
        ord("f"): ord("\f"),
        ord("("): ord("("),
        ord(")"): ord(")"),
        ord("\\"): ord("\\"),
    }
    while pos < end:
        byte = obj[pos]
        if byte != ord("\\"):
            out.append(byte)
            pos += 1
            continue
        pos += 1
        if pos >= end:
            break
        esc = obj[pos]
        if esc in b"\r\n":
            if esc == ord("\r") and pos + 1 < end and obj[pos + 1] == ord("\n"):
                pos += 2
            else:
                pos += 1
            continue
        if ord("0") <= esc <= ord("7"):
            octal = bytes([esc])
            pos += 1
            for _ in range(2):
                if pos < end and ord("0") <= obj[pos] <= ord("7"):
                    octal += bytes([obj[pos]])
                    pos += 1
                else:
                    break
            out.append(int(octal, 8))
            continue
        out.append(escapes.get(esc, esc))
        pos += 1
    return bytes(out)


def _undo_predictor(
    raw: bytes,
    predictor: int,
    columns: int,
    colors: int,
    bits_per_component: int,
    height: int,
) -> bytes:
    row_length = (columns * colors * bits_per_component + 7) // 8
    if predictor == 1:
        expected = row_length * height
        if len(raw) != expected:
            raise PdfImageError(f"Unexpected raw image length {len(raw)}; expected {expected}")
        return raw
    if not 10 <= predictor <= 15:
        raise PdfImageError(f"Unsupported Flate predictor: {predictor}")

    stride = row_length + 1
    expected = stride * height
    if len(raw) != expected:
        raise PdfImageError(f"Unexpected predicted image length {len(raw)}; expected {expected}")

    bpp = max(1, (colors * bits_per_component + 7) // 8)
    out = bytearray()
    prev = bytes(row_length)
    for row in range(height):
        offset = row * stride
        filter_type = raw[offset]
        scanline = bytearray(raw[offset + 1 : offset + stride])
        if filter_type == 0:
            pass
        elif filter_type == 1:
            for i in range(row_length):
                left = scanline[i - bpp] if i >= bpp else 0
                scanline[i] = (scanline[i] + left) & 0xFF
        elif filter_type == 2:
            for i in range(row_length):
                scanline[i] = (scanline[i] + prev[i]) & 0xFF
        elif filter_type == 3:
            for i in range(row_length):
                left = scanline[i - bpp] if i >= bpp else 0
                up = prev[i]
                scanline[i] = (scanline[i] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            for i in range(row_length):
                left = scanline[i - bpp] if i >= bpp else 0
                up = prev[i]
                up_left = prev[i - bpp] if i >= bpp else 0
                scanline[i] = (scanline[i] + _paeth(left, up, up_left)) & 0xFF
        else:
            raise PdfImageError(f"Unsupported PNG predictor filter byte: {filter_type}")
        out.extend(scanline)
        prev = bytes(scanline)
    return bytes(out)


def _paeth(left: int, up: int, up_left: int) -> int:
    p = left + up - up_left
    pa = abs(p - left)
    pb = abs(p - up)
    pc = abs(p - up_left)
    if pa <= pb and pa <= pc:
        return left
    if pb <= pc:
        return up
    return up_left


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)


def make_png_from_compressed_rows(
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
    compressed_rows: bytes,
    palette: bytes | None = None,
) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    parts = [b"\x89PNG\r\n\x1a\n", _png_chunk(b"IHDR", ihdr)]
    if palette is not None:
        parts.append(_png_chunk(b"PLTE", palette))
    parts.append(_png_chunk(b"IDAT", compressed_rows))
    parts.append(_png_chunk(b"IEND", b""))
    return b"".join(parts)


def make_png_from_scanlines(
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
    scanlines: bytes,
    palette: bytes | None = None,
) -> bytes:
    row_length = _png_row_length(width, bit_depth, color_type)
    expected = row_length * height
    if len(scanlines) != expected:
        raise PdfImageError(f"PNG payload length {len(scanlines)}; expected {expected}")

    filtered = bytearray()
    for row in range(height):
        start = row * row_length
        filtered.append(0)
        filtered.extend(scanlines[start : start + row_length])
    return make_png_from_compressed_rows(
        width,
        height,
        bit_depth,
        color_type,
        zlib.compress(bytes(filtered), level=9),
        palette,
    )


def _png_row_length(width: int, bit_depth: int, color_type: int) -> int:
    channels = {0: 1, 2: 3, 3: 1}[color_type]
    return (width * channels * bit_depth + 7) // 8


def images_in_pdf_page_order(pdf_path: Path) -> list[ImageStream]:
    fitz = _load_fitz()
    if fitz is None:
        raise PdfImageError("PyMuPDF is required for PDF page-order image extraction. Install PyMuPDF and try again.")

    doc = fitz.open(pdf_path)
    images: list[ImageStream] = []
    for page in doc:
        page_images = page.get_images(full=True)
        for page_image in page_images:
            xref = page_image[0]
            image = _image_from_xref(doc, xref, len(images) + 1)
            if image is not None:
                images.append(image)

    return images


def _load_fitz():
    try:
        return importlib.import_module("fitz")
    except ModuleNotFoundError:
        return None


def _image_from_xref(doc, xref: int, index: int) -> ImageStream | None:
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
            return ImageStream(
                index=index,
                width=extracted["width"],
                height=extracted["height"],
                bits_per_component=8,
                color_space=b"/DeviceRGB",
                filter_name="PNG",
                decode_parms=None,
                data=extracted["image"],
                xref=xref,
            )
        else:
            raise PdfImageError(f"Unsupported extracted image extension for xref {xref}: {ext}")

    if filter_name == "DCTDecode":
        payload = doc.xref_stream_raw(xref)
        return ImageStream(
            index=index,
            width=_xref_required_int(doc, xref, "Width"),
            height=_xref_required_int(doc, xref, "Height"),
            bits_per_component=_xref_required_int(doc, xref, "BitsPerComponent"),
            color_space=_xref_object(doc, xref, "ColorSpace"),
            filter_name=filter_name,
            decode_parms=_xref_object(doc, xref, "DecodeParms"),
            data=payload,
            xref=xref,
        )

    if filter_name == "FlateDecode":
        payload = doc.xref_stream_raw(xref)
        return ImageStream(
            index=index,
            width=_xref_required_int(doc, xref, "Width"),
            height=_xref_required_int(doc, xref, "Height"),
            bits_per_component=_xref_required_int(doc, xref, "BitsPerComponent"),
            color_space=_normalize_xref_color_space(doc, _xref_object(doc, xref, "ColorSpace")),
            filter_name=filter_name,
            decode_parms=_normalize_pdf_object(_xref_object(doc, xref, "DecodeParms")),
            data=payload,
            xref=xref,
        )

    if filter_name in {"JBIG2Decode"}:
        return _decoded_image_from_xref(doc, xref, index)

    raise PdfImageError(f"Unsupported image filter for xref {xref}: {filter_name}")


def _decoded_image_from_xref(doc, xref: int, index: int) -> ImageStream:
    extracted = doc.extract_image(xref)
    ext = extracted["ext"]
    if ext != "png":
        raise PdfImageError(f"Unsupported extracted image extension for xref {xref}: {ext}")
    return ImageStream(
        index=index,
        width=extracted["width"],
        height=extracted["height"],
        bits_per_component=8,
        color_space=b"/DeviceRGB",
        filter_name="PNG",
        decode_parms=None,
        data=extracted["image"],
        xref=xref,
    )


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


def convert_pdf_to_cbz(pdf_path: Path, cbz_path: Path, overwrite: bool = False) -> dict[str, int]:
    if cbz_path.exists() and not overwrite:
        raise PdfImageError(f"Refusing to overwrite existing file: {cbz_path}")

    images = images_in_pdf_page_order(pdf_path)
    if not images:
        raise PdfImageError(f"No image streams found in {pdf_path}")

    counts = {"jpg": 0, "png": 0}
    padding = max(4, len(str(len(images))))
    with ZipFile(cbz_path, "w", compression=ZIP_STORED) as archive:
        for image in images:
            if image.filter_name == "PNG":
                ext, payload = "png", image.data
            else:
                ext, payload = image_to_archive_member(image)
            counts[ext] = counts.get(ext, 0) + 1
            info = ZipInfo(f"{image.index:0{padding}d}.{ext}")
            info.compress_type = ZIP_STORED
            archive.writestr(info, payload)
    counts["total"] = len(images)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="+", type=Path, help="PDF files to convert")
    parser.add_argument("--overwrite", action="store_true", help="replace existing CBZ files")
    args = parser.parse_args()

    for pdf_path in args.pdfs:
        if pdf_path.suffix.lower() != ".pdf":
            raise PdfImageError(f"Not a PDF file: {pdf_path}")
        cbz_path = pdf_path.with_suffix(".cbz")
        counts = convert_pdf_to_cbz(pdf_path, cbz_path, overwrite=args.overwrite)
        print(
            f"{pdf_path.name} -> {cbz_path.name}: "
            f"{counts['total']} pages ({counts.get('jpg', 0)} jpg, {counts.get('png', 0)} png)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
