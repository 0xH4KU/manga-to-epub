from __future__ import annotations

import math

import cv2
import numpy as np

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.features.common import clamp01


def panel_boundary_penalty(left_page: np.ndarray, right_page: np.ndarray, offset: int) -> float:
    joined = join_for_analysis(left_page, right_page, offset)
    if joined is None:
        return 0.0
    h, w = joined.shape[:2]
    scale = min(1.0, 720.0 / h)
    if scale < 1.0:
        joined = cv2.resize(joined, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        h, w = joined.shape[:2]

    edges = cv2.Canny(joined, 60, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=90,
        minLineLength=max(80, int(min(h, w) * 0.18)),
        maxLineGap=8,
    )
    if lines is None:
        return 0.0

    horizontal = 0.0
    vertical = 0.0
    seam_vertical = 0.0
    seam_x = w // 2
    for item in lines[:300]:
        x1, y1, x2, y2 = item[0]
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length <= 0:
            continue
        angle = abs(math.atan2(dy, dx))
        if angle < 0.08 or abs(angle - math.pi) < 0.08:
            horizontal += min(1.0, length / w)
        elif abs(angle - math.pi / 2) < 0.08:
            vertical += min(1.0, length / h)
            if min(abs(x1 - seam_x), abs(x2 - seam_x)) < w * 0.08:
                seam_vertical += min(1.0, length / h)

    return clamp01(0.10 * horizontal + 0.12 * vertical + 0.42 * seam_vertical)


def page_panel_risk(page: np.ndarray) -> float:
    h, w = page.shape[:2]
    scale = min(1.0, 720.0 / h)
    img = page
    if scale < 1.0:
        img = cv2.resize(page, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]

    edges = cv2.Canny(img, 60, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=80,
        minLineLength=max(70, int(min(h, w) * 0.16)),
        maxLineGap=8,
    )
    if lines is None:
        return 0.0

    horizontal = 0.0
    vertical = 0.0
    for item in lines[:240]:
        x1, y1, x2, y2 = item[0]
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length <= 0:
            continue
        angle = abs(math.atan2(dy, dx))
        if angle < 0.06 or abs(angle - math.pi) < 0.06:
            horizontal += min(1.0, length / w)
        elif abs(angle - math.pi / 2) < 0.06:
            vertical += min(1.0, length / h)

    # Multiple strong horizontal and vertical separators is a better signal for ordinary panel pages
    # than a single page/frame border.
    return clamp01(0.12 * max(0.0, horizontal - 1.1) + 0.12 * max(0.0, vertical - 1.1))


def inner_gutter_risk(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.shape[1], right.shape[1], 36)
    left_inner = left[:, -width:].astype(np.float32)
    right_inner = right[:, :width].astype(np.float32)
    left_white = float((left_inner > 244).mean())
    right_white = float((right_inner > 244).mean())
    left_low = float((cv2.Canny(left_inner.astype(np.uint8), 55, 140) == 0).mean())
    right_low = float((cv2.Canny(right_inner.astype(np.uint8), 55, 140) == 0).mean())
    both_white = math.sqrt(left_white * right_white)
    both_low = math.sqrt(left_low * right_low)
    return clamp01(0.68 * both_white + 0.32 * max(0.0, both_low - 0.78) / 0.22)


def join_for_analysis(left_page: np.ndarray, right_page: np.ndarray, offset: int) -> np.ndarray | None:
    y_left = max(0, offset)
    y_right = max(0, -offset)
    h = min(left_page.shape[0] - y_left, right_page.shape[0] - y_right)
    if h <= 24:
        return None
    left = left_page[y_left : y_left + h, :]
    right = right_page[y_right : y_right + h, :]
    return np.concatenate([left, right], axis=1)
