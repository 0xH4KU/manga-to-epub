from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class PageFeatures:
    page: int
    width: int
    height: int
    ink_ratio: float
    edge_density: float
    blank_ratio: float
    dark_ratio: float
    title_likeness: float
    content_density: float
    center_ink_ratio: float
    border_ink_ratio: float
    bottom_activity: float


def extract_page_features(page: int, image: Image.Image) -> PageFeatures:
    grayscale = image.convert("L")
    data = np.asarray(grayscale, dtype=np.float32) / 255.0
    height, width = data.shape

    ink_mask = data < 0.84
    dark_mask = data < 0.22
    blank_mask = data > 0.94
    edge_map = _edge_map(data)

    center = _center_slice(height, width)
    border = _border_mask(height, width)
    bottom = data[int(height * 0.78) :, :]

    ink_ratio = float(ink_mask.mean())
    edge_density = float((edge_map > 0.12).mean())
    blank_ratio = float(blank_mask.mean())
    dark_ratio = float(dark_mask.mean())
    center_ink_ratio = float(ink_mask[center].mean())
    border_ink_ratio = float(ink_mask[border].mean()) if border.any() else 0.0
    bottom_activity = float(((bottom < 0.84).mean() + (_edge_map(bottom) > 0.12).mean()) / 2)
    content_density = _clamp((ink_ratio * 0.55) + (edge_density * 0.45))
    title_likeness = _title_likeness(blank_ratio, ink_ratio, center_ink_ratio, border_ink_ratio, edge_density)

    return PageFeatures(
        page=page,
        width=width,
        height=height,
        ink_ratio=ink_ratio,
        edge_density=edge_density,
        blank_ratio=blank_ratio,
        dark_ratio=dark_ratio,
        title_likeness=title_likeness,
        content_density=content_density,
        center_ink_ratio=center_ink_ratio,
        border_ink_ratio=border_ink_ratio,
        bottom_activity=bottom_activity,
    )


def visual_difference(left: PageFeatures, right: PageFeatures) -> float:
    differences = (
        abs(left.ink_ratio - right.ink_ratio) * 1.7,
        abs(left.edge_density - right.edge_density) * 1.4,
        abs(left.blank_ratio - right.blank_ratio) * 1.2,
        abs(left.dark_ratio - right.dark_ratio) * 1.1,
        abs(left.center_ink_ratio - right.center_ink_ratio),
        abs(left.bottom_activity - right.bottom_activity),
    )
    return _clamp(sum(differences) / len(differences) * 2.0)


def _edge_map(data: np.ndarray) -> np.ndarray:
    if data.size == 0:
        return data
    vertical = np.zeros_like(data)
    horizontal = np.zeros_like(data)
    vertical[:, 1:] = np.abs(data[:, 1:] - data[:, :-1])
    horizontal[1:, :] = np.abs(data[1:, :] - data[:-1, :])
    return np.maximum(vertical, horizontal)


def _center_slice(height: int, width: int) -> tuple[slice, slice]:
    y0 = int(height * 0.25)
    y1 = int(height * 0.75)
    x0 = int(width * 0.22)
    x1 = int(width * 0.78)
    return slice(y0, y1), slice(x0, x1)


def _border_mask(height: int, width: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    y = max(1, int(height * 0.12))
    x = max(1, int(width * 0.12))
    mask[:y, :] = True
    mask[-y:, :] = True
    mask[:, :x] = True
    mask[:, -x:] = True
    return mask


def _title_likeness(
    blank_ratio: float,
    ink_ratio: float,
    center_ink_ratio: float,
    border_ink_ratio: float,
    edge_density: float,
) -> float:
    sparse = max(0.0, 1.0 - abs(ink_ratio - 0.05) / 0.18)
    centered = _clamp((center_ink_ratio - border_ink_ratio) * 5.0)
    quiet = _clamp(1.0 - edge_density * 5.0)
    blank = _clamp((blank_ratio - 0.62) / 0.35)
    return _clamp(blank * 0.34 + sparse * 0.24 + centered * 0.26 + quiet * 0.16)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
