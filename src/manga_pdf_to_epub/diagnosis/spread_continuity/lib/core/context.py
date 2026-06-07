from __future__ import annotations

import re
from dataclasses import replace
from typing import Any


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def page_number(name: str) -> int | None:
    numbers = re.findall(r"\d+", name)
    return int(numbers[-1]) if numbers else None


def adjacent_span(score: Any) -> tuple[int, int] | None:
    right_num = page_number(score.right_name)
    left_num = page_number(score.left_name)
    if right_num is None or left_num is None or abs(right_num - left_num) != 1:
        return None
    start = min(right_num, left_num)
    return start, start + 1


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def contextual_values(score: Any, competitors: list[Any]) -> tuple[float, float, float]:
    if not competitors:
        return score.spread, score.review_score, 0.0

    best_competitor = max(item.spread for item in competitors)
    local_margin = score.spread - best_competitor

    ambiguity_penalty = clamp01((0.04 - local_margin) / 0.12) * 0.10
    near_tie_count = sum(1 for item in competitors if item.spread >= score.spread - 0.05)
    promiscuity_penalty = clamp01((near_tie_count - 1) / 3.0) * 0.04
    context_penalty = clamp01(ambiguity_penalty + promiscuity_penalty)

    peak_boost = clamp01((local_margin - 0.12) / 0.10) * 0.015
    adjusted_spread = clamp01(score.spread * (1.0 - context_penalty) + peak_boost)
    adjusted_review = clamp01(score.review_score * (1.0 - context_penalty * 0.72) + peak_boost)
    return adjusted_spread, adjusted_review, local_margin


def apply_contextual_adjustment(scores: list[Any]) -> list[Any]:
    spans = [(score, adjacent_span(score)) for score in scores]
    adjusted = []
    for score, span in spans:
        if span is None:
            adjusted.append(
                replace(
                    score,
                    raw_spread=score.spread,
                    raw_review_score=score.review_score,
                    local_margin=0.0,
                    context_penalty=0.0,
                    context_boost=0.0,
                )
            )
            continue

        competitors = [
            other
            for other, other_span in spans
            if other is not score and other_span is not None and overlaps(span, other_span)
        ]
        adjusted_spread, adjusted_review, local_margin = contextual_values(score, competitors)
        context_penalty = 0.0 if score.spread <= 0 else max(0.0, 1.0 - adjusted_spread / score.spread)
        context_boost = max(0.0, adjusted_spread - score.spread)
        adjusted.append(
            replace(
                score,
                spread=adjusted_spread,
                review_score=adjusted_review,
                raw_spread=score.spread,
                raw_review_score=score.review_score,
                local_margin=local_margin,
                context_penalty=context_penalty,
                context_boost=context_boost,
            )
        )
    return adjusted


def attach_raw_scores(scores: list[Any]) -> list[Any]:
    return [
        replace(
            score,
            raw_spread=score.spread,
            raw_review_score=score.review_score,
            local_margin=0.0,
            context_penalty=0.0,
            context_boost=0.0,
        )
        for score in scores
    ]
