from __future__ import annotations

import math

import cv2
import numpy as np

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.features.common import clamp01, signed_corr01


def composition_spread_score(left_page: np.ndarray, right_page: np.ndarray, offset: int) -> float:
    """Detect spreads where the seam itself is blank but the large composition crosses it."""
    y_left = max(0, offset)
    y_right = max(0, -offset)
    h = min(left_page.shape[0] - y_left, right_page.shape[0] - y_right)
    if h <= 80:
        return 0.0

    left = left_page[y_left : y_left + h, :]
    right = right_page[y_right : y_right + h, :]
    l_w = left.shape[1]
    r_w = right.shape[1]
    gutter_l = max(8, int(l_w * 0.055))
    gutter_r = max(8, int(r_w * 0.055))
    span_l = max(24, int(l_w * 0.42))
    span_r = max(24, int(r_w * 0.42))
    if span_l <= gutter_l or span_r <= gutter_r:
        return 0.0

    left_roi = left[:, max(0, l_w - gutter_l - span_l) : l_w - gutter_l]
    right_roi = right[:, gutter_r : min(r_w, gutter_r + span_r)]
    if left_roi.size == 0 or right_roi.size == 0:
        return 0.0

    left_mask = large_ink_mask(left_roi)
    right_mask = large_ink_mask(right_roi)
    left_density = left_mask.mean(axis=1).astype(np.float32)
    right_density = right_mask.mean(axis=1).astype(np.float32)
    left_mass = float(left_mask.mean())
    right_mass = float(right_mask.mean())
    mass = (left_mass + right_mass) * 0.5
    if mass < 0.018:
        return 0.0

    overlap = float(np.minimum(left_density, right_density).sum() / (np.maximum(left_density, right_density).sum() + 1e-6))
    corr = signed_corr01(left_density, right_density)
    left_active = left_density > 0.025
    right_active = right_density > 0.025
    active_union = float((left_active | right_active).mean())
    active_overlap = float((left_active & right_active).mean())
    jaccard = active_overlap / (active_union + 1e-6)

    ys = np.arange(h, dtype=np.float32)
    left_y = float((ys * left_density).sum() / (left_density.sum() + 1e-6))
    right_y = float((ys * right_density).sum() / (right_density.sum() + 1e-6))
    centroid_score = math.exp(-abs(left_y - right_y) / max(1.0, h * 0.11))

    seam_left = left[:, l_w - gutter_l : l_w]
    seam_right = right[:, :gutter_r]
    seam_blank = (float((seam_left > 244).mean()) + float((seam_right > 244).mean())) * 0.5
    seam_detail = 1.0 - seam_blank

    mass_score = clamp01(mass / 0.16)
    balance = math.sqrt(min(left_mass, right_mass) / (max(left_mass, right_mass) + 1e-6))
    raw = (
        0.27 * overlap
        + 0.20 * corr
        + 0.20 * jaccard
        + 0.13 * centroid_score
        + 0.12 * mass_score
        + 0.08 * balance
    )

    # Composition spreads often have a deliberate white binding area. Still, a fully
    # blank seam needs strong evidence away from the seam before it should count.
    if seam_blank > 0.90:
        raw *= 0.68 + 0.32 * min(overlap, jaccard, mass_score)
    else:
        raw *= 0.86 + 0.14 * seam_detail
    return clamp01(raw)


def large_ink_mask(gray: np.ndarray) -> np.ndarray:
    mask = (gray < 122).astype(np.uint8)
    if mask.size == 0:
        return mask
    h, w = mask.shape[:2]
    close_size = max(3, min(15, round(min(h, w) * 0.018)))
    if close_size % 2 == 0:
        close_size += 1
    open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)
    return mask
