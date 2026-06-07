from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ReliabilitySignals:
    stability: float | None = None


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def pair_key(score: Any) -> str:
    return f"{score.right_name}|{score.left_name}"


def stability_from_scores(scores: list[float]) -> float:
    if len(scores) <= 1:
        return 1.0
    values = np.asarray(scores, dtype=np.float32)
    spread = float(values.max() - values.min())
    std = float(values.std())
    return clamp01(1.0 - spread / 0.35 - std / 0.22)


def robust_relative_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    arr = np.asarray(values, dtype=np.float32)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    scale = max(0.035, 1.4826 * mad)
    z = (arr - median) / scale
    return [clamp01((float(item) + 0.6) / 3.2) for item in z]


def apply_reliability_adjustment(
    scores: list[Any],
    signals_by_pair: dict[str, ReliabilitySignals] | None = None,
) -> list[Any]:
    signals_by_pair = signals_by_pair or {}
    relatives = robust_relative_scores([score.spread for score in scores])
    adjusted = []
    for score, relative in zip(scores, relatives, strict=False):
        signals = signals_by_pair.get(pair_key(score), ReliabilitySignals())
        stability = signals.stability
        instability_penalty = 0.0 if stability is None else clamp01((0.55 - stability) / 0.55) * 0.055
        relative_boost = clamp01((relative - 0.74) / 0.26) * 0.020
        distinctiveness_gate = clamp01((relative - 0.74) / 0.16)
        stable_boost = (
            0.0
            if stability is None
            else clamp01((stability - 0.88) / 0.12) * 0.012 * distinctiveness_gate
        )
        reliability_boost = relative_boost + stable_boost
        adjusted_spread = clamp01(score.spread * (1.0 - instability_penalty) + reliability_boost)
        adjusted_review = clamp01(score.review_score * (1.0 - instability_penalty * 0.7) + reliability_boost)
        raw_spread = score.raw_spread or score.spread
        raw_review_score = score.raw_review_score or score.review_score
        adjusted.append(
            replace(
                score,
                spread=adjusted_spread,
                review_score=adjusted_review,
                raw_spread=raw_spread,
                raw_review_score=raw_review_score,
                stability_score=stability or 0.0,
                relative_score=relative,
                reliability_penalty=instability_penalty,
                reliability_boost=reliability_boost,
            )
        )
    return adjusted


def conservative_content_crop(
    bgr: np.ndarray,
    gray: np.ndarray,
    padding: int = 8,
    max_crop_ratio: float = 0.25,
) -> tuple[np.ndarray, np.ndarray]:
    h, w = gray.shape[:2]
    non_border = gray < 245
    ys, xs = np.where(non_border)
    if len(xs) == 0 or len(ys) == 0:
        return bgr, gray

    x0 = max(0, int(xs.min()) - padding)
    x1 = min(w, int(xs.max()) + padding + 1)
    y0 = max(0, int(ys.min()) - padding)
    y1 = min(h, int(ys.max()) + padding + 1)

    max_x_crop = int(w * max_crop_ratio)
    max_y_crop = int(h * max_crop_ratio)
    x0 = min(x0, max_x_crop)
    y0 = min(y0, max_y_crop)
    x1 = max(x1, w - max_x_crop)
    y1 = max(y1, h - max_y_crop)

    if x1 - x0 < max(1, int(w * 0.65)) or y1 - y0 < max(1, int(h * 0.65)):
        return bgr, gray
    return bgr[y0:y1, x0:x1], gray[y0:y1, x0:x1]


def make_trimmed_page(page: Any, page_type: type[Any]) -> Any:
    cropped_bgr, cropped_gray = conservative_content_crop(page.bgr, page.gray)
    if cropped_gray.shape == page.gray.shape:
        return page
    return page_type(page.name, page.path, cropped_bgr, cropped_gray)
