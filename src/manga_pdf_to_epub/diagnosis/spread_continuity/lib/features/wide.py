from __future__ import annotations

import math

import cv2
import numpy as np

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.features.common import clamp01, edge_density_profile, exp_score, signed_corr01


def profile_correlation_score(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.shape[1], right.shape[1], 80)
    trim = max(1, left.shape[0] // 40)
    left_roi = left[trim:-trim, -width:].astype(np.float32)
    right_roi = right[trim:-trim, :width].astype(np.float32)
    if left_roi.shape[0] < 8:
        return 0.25

    left_brightness = left_roi.mean(axis=1)
    right_brightness = right_roi.mean(axis=1)
    left_ink = np.maximum(0.0, 210.0 - left_roi).mean(axis=1)
    right_ink = np.maximum(0.0, 210.0 - right_roi).mean(axis=1)
    left_edge = edge_density_profile(left_roi, True, width)
    right_edge = edge_density_profile(right_roi, False, width)

    scores = [
        signed_corr01(left_brightness, right_brightness),
        signed_corr01(left_ink, right_ink),
        signed_corr01(left_edge, right_edge),
    ]
    return float(np.mean(scores))


def gradient_energy_balance_score(left: np.ndarray, right: np.ndarray) -> float:
    le = edge_density_profile(left, True, min(left.shape[1], 80))
    re = edge_density_profile(right, False, min(right.shape[1], 80))
    left_energy = float(np.percentile(le, 62))
    right_energy = float(np.percentile(re, 62))
    stronger = max(left_energy, right_energy)
    weaker = min(left_energy, right_energy)
    if stronger < 10:
        return 0.35
    return clamp01(math.sqrt(weaker / (stronger + 1e-6)))


def orientation_histogram(strip: np.ndarray, from_right: bool, sample_width: int) -> tuple[np.ndarray, float]:
    width = min(sample_width, strip.shape[1])
    roi = strip[:, -width:] if from_right else strip[:, :width]
    gx = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
    mag, angle = cv2.cartToPolar(gx, gy, angleInDegrees=False)
    angle = np.mod(angle, np.pi)
    mask = mag > 28
    if not np.any(mask):
        return np.zeros(8, dtype=np.float32), 0.0
    bins = np.floor(angle[mask] / np.pi * 8).astype(np.int32)
    bins = np.clip(bins, 0, 7)
    hist = np.bincount(bins, weights=mag[mask].astype(np.float64), minlength=8).astype(np.float32)
    return hist, float(hist.sum())


def orientation_field_score(left: np.ndarray, right: np.ndarray) -> float:
    lh, lsum = orientation_histogram(left, True, min(left.shape[1], 90))
    rh, rsum = orientation_histogram(right, False, min(right.shape[1], 90))
    if lsum < 500 or rsum < 500:
        return 0.25
    denom = float(np.linalg.norm(lh) * np.linalg.norm(rh))
    if denom <= 1e-6:
        return 0.25
    return clamp01(float(np.dot(lh, rh) / denom))


def line_continuation_score(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.shape[1], right.shape[1], 120)
    lroi = left[:, -width:].astype(np.uint8)
    rroi = right[:, :width].astype(np.uint8)
    l_edges = cv2.Canny(lroi, 60, 150)
    r_edges = cv2.Canny(rroi, 60, 150)
    l_lines = cv2.HoughLinesP(l_edges, 1, np.pi / 180, threshold=35, minLineLength=28, maxLineGap=8)
    r_lines = cv2.HoughLinesP(r_edges, 1, np.pi / 180, threshold=35, minLineLength=28, maxLineGap=8)
    if l_lines is None or r_lines is None:
        return 0.25

    left_candidates = []
    for item in l_lines[:160]:
        x1, y1, x2, y2 = item[0]
        if max(x1, x2) < width - 18:
            continue
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < 28:
            continue
        angle = math.atan2(dy, dx)
        if abs(abs(angle) - math.pi / 2) < 0.22:
            continue
        x_edge = max(x1, x2)
        y_edge = y1 if x1 >= x2 else y2
        left_candidates.append((angle, y_edge, length, width - x_edge))

    right_candidates = []
    for item in r_lines[:160]:
        x1, y1, x2, y2 = item[0]
        if min(x1, x2) > 18:
            continue
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < 28:
            continue
        angle = math.atan2(dy, dx)
        if abs(abs(angle) - math.pi / 2) < 0.22:
            continue
        x_edge = min(x1, x2)
        y_edge = y1 if x1 <= x2 else y2
        right_candidates.append((angle, y_edge, length, x_edge))

    if not left_candidates or not right_candidates:
        return 0.25

    best = 0.0
    for la, ly, llen, ldist in left_candidates:
        for ra, ry, rlen, rdist in right_candidates:
            angle_diff = abs(math.atan2(math.sin(la - ra), math.cos(la - ra)))
            angle_diff = min(angle_diff, abs(math.pi - angle_diff))
            if angle_diff > 0.35:
                continue
            y_diff = abs(ly - ry)
            if y_diff > 28:
                continue
            score = math.exp(-angle_diff / 0.18) * math.exp(-y_diff / 16.0)
            score *= min(1.0, (llen + rlen) / 120.0)
            score *= math.exp(-(ldist + rdist) / 16.0)
            best = max(best, score)
    return clamp01(0.25 + 0.75 * best)


def texture_score(left: np.ndarray, right: np.ndarray) -> float:
    width = min(left.shape[1], right.shape[1], 90)
    lroi = left[:, -width:].astype(np.float32)
    rroi = right[:, :width].astype(np.float32)
    scores = []
    for theta in (0, np.pi / 4, np.pi / 2, 3 * np.pi / 4):
        for lambd in (6, 10, 16):
            kernel = cv2.getGaborKernel((17, 17), 4.0, theta, lambd, 0.5, 0, ktype=cv2.CV_32F)
            le = np.abs(cv2.filter2D(lroi, cv2.CV_32F, kernel)).mean()
            re = np.abs(cv2.filter2D(rroi, cv2.CV_32F, kernel)).mean()
            stronger = max(float(le), float(re))
            weaker = min(float(le), float(re))
            if stronger < 1e-6:
                scores.append(0.35)
            else:
                scores.append(math.sqrt(weaker / stronger))
    return clamp01(float(np.mean(scores)))


def color_style_score(left_bgr: np.ndarray, right_bgr: np.ndarray) -> float:
    left_hsv = cv2.cvtColor(left_bgr, cv2.COLOR_BGR2HSV)
    right_hsv = cv2.cvtColor(right_bgr, cv2.COLOR_BGR2HSV)
    left_lab = cv2.cvtColor(left_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    right_lab = cv2.cvtColor(right_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)

    left_sat = left_hsv[:, :, 1].astype(np.float32)
    right_sat = right_hsv[:, :, 1].astype(np.float32)
    left_color_frac = float((left_sat > 28).mean())
    right_color_frac = float((right_sat > 28).mean())
    sat_score = exp_score(abs(float(np.percentile(left_sat, 75)) - float(np.percentile(right_sat, 75))), 32.0)
    frac_score = exp_score(abs(left_color_frac - right_color_frac), 0.18)

    # Compare chroma channels but downweight near-white paper regions.
    left_mask = left_bgr.mean(axis=2) < 248
    right_mask = right_bgr.mean(axis=2) < 248
    if left_mask.any() and right_mask.any():
        left_ab = left_lab[left_mask][:, 1:3].mean(axis=0)
        right_ab = right_lab[right_mask][:, 1:3].mean(axis=0)
        ab_score = exp_score(float(np.linalg.norm(left_ab - right_ab)), 18.0)
    else:
        ab_score = 0.5
    return clamp01(0.45 * sat_score + 0.40 * frac_score + 0.15 * ab_score)
