from __future__ import annotations

from dataclasses import dataclass

from .features import PageFeatures


@dataclass(frozen=True)
class GapScore:
    gap_after_page: int
    gap_before_page: int
    safe_insert_score: float
    label: str
    visual_difference: float
    continuity_risk: float
    reasons: tuple[str, ...]


def score_gap(
    *,
    left: PageFeatures,
    right: PageFeatures,
    previous: PageFeatures | None,
    next_page: PageFeatures | None,
    visual_difference: float,
    left_continuity: float | None,
    right_continuity: float | None,
) -> GapScore:
    reasons: list[str] = []
    context_missing = previous is None or next_page is None

    low_content = max(left.blank_ratio, right.blank_ratio)
    left_dark_pause = _is_dark_pause(left)
    right_dark_pause = _is_dark_pause(right)
    dark_pause = left_dark_pause or right_dark_pause
    sparse_dramatic = _is_sparse_dramatic(left) or _is_sparse_dramatic(right)
    avg_density = (left.content_density + right.content_density) / 2
    title_likeness = max(left.title_likeness, right.title_likeness)
    climax_density = max(left.content_density, right.content_density)
    continuity_risk = _continuity_risk(visual_difference, left_continuity, right_continuity)
    if dark_pause:
        continuity_risk = min(continuity_risk, 0.42)

    score = 0.18
    score += visual_difference * 0.28
    score += low_content * 0.34
    score += max(0.0, 0.55 - avg_density) * 0.38
    score += title_likeness * 0.22
    score -= continuity_risk * 0.28
    score -= max(0.0, climax_density - 0.62) * 0.30

    if low_content >= 0.68 or avg_density <= 0.16:
        reasons.append("low content")
        score += 0.12
    if title_likeness >= 0.65:
        reasons.append("title-like page")
        score += 0.16
    if left_dark_pause:
        reasons.append("dark pause page")
        score += 0.48
    elif right_dark_pause:
        reasons.append("dark pause follows")
        score += 0.30
    if visual_difference >= 0.58:
        reasons.append("visual discontinuity")
        score += 0.05
    if continuity_risk >= 0.68:
        reasons.append("high continuity risk")
        score -= 0.18
    if climax_density >= 0.62 and low_content <= 0.12 and not dark_pause:
        reasons.append("dense adjacent pages")
        score -= 0.12
    if sparse_dramatic and continuity_risk >= 0.58 and title_likeness < 0.5 and not dark_pause:
        reasons.append("sparse dramatic content")
        score -= 0.22
    if context_missing:
        reasons.append("edge context missing")
        score += 0.03

    score = _clamp(score)
    return GapScore(
        gap_after_page=left.page,
        gap_before_page=right.page,
        safe_insert_score=score,
        label=_label_for(score, title_likeness, low_content, visual_difference, continuity_risk),
        visual_difference=_clamp(visual_difference),
        continuity_risk=continuity_risk,
        reasons=tuple(reasons or ["balanced visual pause"]),
    )


def score_gaps(features: list[PageFeatures]) -> list[GapScore]:
    gaps: list[GapScore] = []
    for index in range(len(features) - 1):
        left = features[index]
        right = features[index + 1]
        previous = features[index - 1] if index > 0 else None
        next_page = features[index + 2] if index + 2 < len(features) else None
        gap_difference = _feature_difference(left, right)
        left_continuity = _continuity_from_pair(previous, left) if previous is not None else None
        right_continuity = _continuity_from_pair(right, next_page) if next_page is not None else None
        gaps.append(
            score_gap(
                left=left,
                right=right,
                previous=previous,
                next_page=next_page,
                visual_difference=gap_difference,
                left_continuity=left_continuity,
                right_continuity=right_continuity,
            )
        )
    return gaps


def _continuity_risk(
    visual_difference: float,
    left_continuity: float | None,
    right_continuity: float | None,
) -> float:
    continuity_values = [1.0 - _clamp(visual_difference)]
    if left_continuity is not None:
        continuity_values.append(_clamp(left_continuity))
    if right_continuity is not None:
        continuity_values.append(_clamp(right_continuity))
    return max(continuity_values)


def _continuity_from_pair(left: PageFeatures, right: PageFeatures) -> float:
    return 1.0 - _feature_difference(left, right)


def _feature_difference(left: PageFeatures, right: PageFeatures) -> float:
    differences = (
        abs(left.ink_ratio - right.ink_ratio) * 1.7,
        abs(left.edge_density - right.edge_density) * 1.4,
        abs(left.blank_ratio - right.blank_ratio) * 1.2,
        abs(left.dark_ratio - right.dark_ratio) * 1.1,
        abs(left.center_ink_ratio - right.center_ink_ratio),
        abs(left.bottom_activity - right.bottom_activity),
    )
    return _clamp(sum(differences) / len(differences) * 2.0)


def _label_for(
    score: float,
    title_likeness: float,
    low_content: float,
    visual_difference: float,
    continuity_risk: float,
) -> str:
    if continuity_risk >= 0.82 and score <= 0.35:
        return "F do_not_insert"
    if title_likeness >= 0.65 and score >= 0.72:
        return "A chapter_boundary"
    if low_content >= 0.68 and score >= 0.58:
        return "B low_content_pause"
    if score >= 0.7 and visual_difference >= 0.55:
        return "C scene_change"
    if score >= 0.5 and visual_difference >= 0.45:
        return "D visual_discontinuity"
    if score <= 0.3:
        return "F do_not_insert"
    return "E risky_continuity"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _is_dark_pause(page: PageFeatures) -> bool:
    return page.dark_ratio >= 0.82 and page.edge_density <= 0.04


def _is_sparse_dramatic(page: PageFeatures) -> bool:
    return (
        page.blank_ratio >= 0.66
        and page.ink_ratio >= 0.14
        and page.edge_density >= 0.08
        and page.title_likeness < 0.5
        and page.center_ink_ratio >= 0.18
    )
