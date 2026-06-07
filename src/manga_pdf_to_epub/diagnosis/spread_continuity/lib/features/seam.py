from __future__ import annotations

import math

import cv2
import numpy as np

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.features.common import clamp01, edge_density_profile, exp_score, signed_corr01


def boundary_color_score(left: np.ndarray, right: np.ndarray) -> float:
    widths = [k for k in (0, 1, 2, 4, 8) if k < left.shape[1] and k < right.shape[1]]
    diffs = [np.abs(left[:, -1 - k] - right[:, k]) for k in widths]
    diff = np.concatenate(diffs)
    return exp_score(float(np.percentile(diff, 55)), 42.0)


def gradient_score(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape[1] < 3 or right.shape[1] < 3:
        return 0.0
    seam = np.abs(right[:, 0] - left[:, -1])
    inner = (np.abs(left[:, -1] - left[:, -2]) + np.abs(right[:, 1] - right[:, 0])) * 0.5
    seam_median = float(np.percentile(seam, 55))
    inner_median = float(np.percentile(inner, 55))
    expected = max(8.0, inner_median * 1.8)
    return exp_score(max(0.0, seam_median - expected), 30.0)


def row_profile_score(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.shape[1], right.shape[1], 24)
    trim = max(1, left.shape[0] // 40)
    left_profile = left[trim:-trim, -width:].mean(axis=1)
    right_profile = right[trim:-trim, :width].mean(axis=1)
    return exp_score(float(np.percentile(np.abs(left_profile - right_profile), 60)), 34.0)


def edge_score(left: np.ndarray, right: np.ndarray) -> float:
    le = edge_density_profile(left, True, 12)
    re = edge_density_profile(right, False, 12)
    energy = (le + re) * 0.5
    if float(np.percentile(energy, 60)) < 10:
        return 0.35
    return exp_score(float(np.percentile(np.abs(le - re), 60)), 30.0)


def dark_ink_profile_score(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.shape[1], right.shape[1], 56)
    trim = max(1, left.shape[0] // 40)
    li = np.maximum(0.0, 205.0 - left[trim:-trim, -width:]) / 205.0
    ri = np.maximum(0.0, 205.0 - right[trim:-trim, :width]) / 205.0
    diff = np.abs(li.mean(axis=1) - ri.mean(axis=1))
    return exp_score(float(np.percentile(diff, 65)), 0.18)


def seam_barrier_score(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.shape[1], right.shape[1], 14)
    lm = left[:, -width:].mean(axis=1)
    rm = right[:, :width].mean(axis=1)
    both_white = (lm > 244) & (rm > 244)
    both_black = (lm < 11) & (rm < 11)
    low_detail = ((edge_density_profile(left, True, width) + edge_density_profile(right, False, width)) * 0.5) < 8

    def longest_run(mask: np.ndarray) -> float:
        best = current = 0
        for value in mask.tolist():
            if value:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best / max(1, len(mask))

    run_penalty = max(longest_run(both_white), longest_run(both_black))
    fill_penalty = max(float(both_white.mean()), float(both_black.mean()))
    detail_penalty = float(low_detail.mean())
    return clamp01(0.52 * run_penalty + 0.33 * fill_penalty + 0.15 * detail_penalty)


def seam_activity_score(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.shape[1], right.shape[1], 48)
    left_roi = left[:, -width:].astype(np.uint8)
    right_roi = right[:, :width].astype(np.uint8)
    left_edges = cv2.Canny(left_roi, 55, 140)
    right_edges = cv2.Canny(right_roi, 55, 140)
    left_density = float((left_edges > 0).mean())
    right_density = float((right_edges > 0).mean())
    density = (left_density + right_density) * 0.5
    balance = min(left_density, right_density) / (max(left_density, right_density) + 1e-6)
    density_score = clamp01((density - 0.018) / 0.07)
    return clamp01(0.72 * density_score + 0.28 * math.sqrt(balance))


def seam_contact_score(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.shape[1], right.shape[1], 32)
    if width < 8:
        return 0.0

    left_roi = left[:, -width:].astype(np.uint8)
    right_roi = right[:, :width].astype(np.uint8)
    left_edges = cv2.Canny(left_roi, 55, 140) > 0
    right_edges = cv2.Canny(right_roi, 55, 140) > 0

    # Allow a small vertical tolerance for page scan/crop mismatch.
    kernel = np.ones((5, 1), dtype=np.uint8)
    left_edges = cv2.dilate(left_edges.astype(np.uint8), kernel) > 0
    right_edges = cv2.dilate(right_edges.astype(np.uint8), kernel) > 0

    def contact_fraction(distance: int) -> float:
        distance = min(distance, width)
        left_rows = left_edges[:, -distance:].any(axis=1)
        right_rows = right_edges[:, :distance].any(axis=1)
        return float((left_rows & right_rows).mean())

    contact_near = contact_fraction(12)
    contact_wide = contact_fraction(24)

    bins = 32
    h = left_edges.shape[0]
    step = h / bins
    active_bins = 0
    for i in range(bins):
        y0 = int(round(i * step))
        y1 = int(round((i + 1) * step))
        if y1 <= y0:
            continue
        left_density = float(left_edges[y0:y1].mean())
        right_density = float(right_edges[y0:y1].mean())
        if left_density > 0.015 and right_density > 0.015:
            active_bins += 1

    bin_fraction = active_bins / bins
    return clamp01(0.48 * math.sqrt(contact_near) + 0.32 * math.sqrt(contact_wide) + 0.20 * bin_fraction)


def patch_ncc_score(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.shape[1], right.shape[1], 72)
    lroi = left[:, -width:].astype(np.float32)
    rroi = right[:, :width].astype(np.float32)
    h = min(lroi.shape[0], rroi.shape[0])
    block_h = max(36, h // 18)
    step = max(18, block_h // 2)
    scores = []
    for y in range(0, max(1, h - block_h + 1), step):
        lp = lroi[y : y + block_h, :]
        rp = cv2.flip(rroi[y : y + block_h, :], 1)
        if lp.shape != rp.shape:
            continue
        edge_l = edge_density_profile(lp, True, width).mean()
        edge_r = edge_density_profile(rp, False, width).mean()
        if max(edge_l, edge_r) < 8:
            continue
        scores.append(signed_corr01(lp.reshape(-1), rp.reshape(-1)))
    if not scores:
        return 0.25
    high_fraction = sum(1 for score in scores if score > 0.58) / len(scores)
    return clamp01(0.55 * float(np.percentile(scores, 75)) + 0.45 * high_fraction)
