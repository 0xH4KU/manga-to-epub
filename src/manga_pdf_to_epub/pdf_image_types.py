from __future__ import annotations

from dataclasses import dataclass


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
