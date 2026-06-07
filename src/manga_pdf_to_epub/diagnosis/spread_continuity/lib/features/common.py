from __future__ import annotations

import math

import cv2
import numpy as np


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def exp_score(distance: float, scale: float) -> float:
    return math.exp(-max(0.0, distance) / scale)


def make_strips(left: np.ndarray, right: np.ndarray, ratio: float, offset: int) -> tuple[np.ndarray, np.ndarray] | None:
    band = max(8, int(min(left.shape[1], right.shape[1]) * ratio))
    y_left = max(0, offset)
    y_right = max(0, -offset)
    h = min(left.shape[0] - y_left, right.shape[0] - y_right)
    if h <= 24:
        return None
    left_strip = left[y_left : y_left + h, left.shape[1] - band : left.shape[1]].astype(np.float32)
    right_strip = right[y_right : y_right + h, 0:band].astype(np.float32)
    return left_strip, right_strip


def make_color_strips(left: np.ndarray, right: np.ndarray, ratio: float, offset: int) -> tuple[np.ndarray, np.ndarray] | None:
    band = max(8, int(min(left.shape[1], right.shape[1]) * ratio))
    y_left = max(0, offset)
    y_right = max(0, -offset)
    h = min(left.shape[0] - y_left, right.shape[0] - y_right)
    if h <= 24:
        return None
    left_strip = left[y_left : y_left + h, left.shape[1] - band : left.shape[1]].astype(np.uint8)
    right_strip = right[y_right : y_right + h, 0:band].astype(np.uint8)
    return left_strip, right_strip


def signed_corr01(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    if a.size < 4 or b.size < 4:
        return 0.25
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom < 1e-6:
        return 0.35
    corr = float(np.dot(a, b) / denom)
    return clamp01((corr + 1.0) * 0.5)


def edge_density_profile(strip: np.ndarray, from_right: bool, sample_width: int) -> np.ndarray:
    width = min(sample_width, strip.shape[1])
    roi = strip[:, -width:] if from_right else strip[:, :width]
    gx = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    return mag.mean(axis=1)
