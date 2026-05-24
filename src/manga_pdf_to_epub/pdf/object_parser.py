from __future__ import annotations

import re
from pathlib import Path

from .image_types import ImageStream, PdfImageError


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


def extract_int(dictionary: bytes, key: bytes) -> int | None:
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
        length = extract_int(dictionary, b"Length")
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

        images.append(
            ImageStream(
                index=len(images) + 1,
                width=_extract_required_int(dictionary, b"Width"),
                height=_extract_required_int(dictionary, b"Height"),
                bits_per_component=_extract_required_int(dictionary, b"BitsPerComponent"),
                color_space=_extract_object(dictionary, b"ColorSpace"),
                filter_name=_extract_filter_name(dictionary),
                decode_parms=_extract_object(dictionary, b"DecodeParms"),
                data=raw,
            )
        )
    return images


def _extract_required_int(dictionary: bytes, key: bytes) -> int:
    value = extract_int(dictionary, key)
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


def decode_pdf_literal_string(obj: bytes) -> bytes:
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
