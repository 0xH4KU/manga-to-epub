from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


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
    data: bytes | None
    xref: int | None = None
    data_loader: Callable[[], bytes] | None = None

    def load_data(self) -> bytes:
        if self.data is not None:
            return self.data
        if self.data_loader is not None:
            return self.data_loader()
        raise PdfImageError(f"Image {self.index} has no payload data")
