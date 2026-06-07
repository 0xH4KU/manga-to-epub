from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import Page


SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def natural_key(path: Path) -> list[object]:
    parts = re.split(r"(\d+)", path.name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def list_images(input_dir: Path) -> list[Path]:
    return sorted(
        [p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS],
        key=natural_key,
    )


def load_page(path: Path, max_height: int) -> Page:
    bgr = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"cannot load image: {path}")
    h, w = bgr.shape[:2]
    if h > max_height:
        scale = max_height / h
        bgr = cv2.resize(bgr, (max(1, round(w * scale)), max_height), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return Page(path.stem, path, bgr.astype(np.uint8), gray.astype(np.uint8))


def resize_page(page: Page, max_height: int) -> Page:
    h, w = page.gray.shape[:2]
    if h <= max_height:
        return page
    scale = max_height / h
    size = (max(1, round(w * scale)), max_height)
    bgr = cv2.resize(page.bgr, size, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return Page(page.name, page.path, bgr.astype(np.uint8), gray.astype(np.uint8))


def build_candidate_pairs(
    pages: list[Page],
    right_pages: list[Page],
    left_pages: list[Page],
    pair_mode: str,
    reading: str,
) -> list[tuple[Page, Page]]:
    if pair_mode == "cross":
        return [(right, left) for right in right_pages for left in left_pages if right.path != left.path]

    pairs: list[tuple[Page, Page]] = []
    has_side_names = any("-R" in page.name.upper() or "-L" in page.name.upper() for page in pages)
    for first, second in zip(pages, pages[1:]):
        if has_side_names:
            first_is_right = "-R" in first.name.upper()
            second_is_left = "-L" in second.name.upper()
            first_is_left = "-L" in first.name.upper()
            second_is_right = "-R" in second.name.upper()
            if first_is_right and second_is_left:
                pairs.append((first, second))
            elif first_is_left and second_is_right:
                pairs.append((second, first))
        elif reading == "rtl":
            pairs.append((first, second))
        else:
            pairs.append((second, first))
    return pairs
