from __future__ import annotations

import re

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.features.common import make_color_strips, make_strips
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.features.composition import composition_spread_score
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.features.layout import (
    inner_gutter_risk,
    page_panel_risk,
    panel_boundary_penalty,
)
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.features.seam import (
    boundary_color_score,
    dark_ink_profile_score,
    edge_score,
    gradient_score,
    patch_ncc_score,
    row_profile_score,
    seam_activity_score,
    seam_barrier_score,
    seam_contact_score,
)
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.features.wide import (
    color_style_score,
    gradient_energy_balance_score,
    line_continuation_score,
    orientation_field_score,
    profile_correlation_score,
    texture_score,
)
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.score_model import combine, combine_review_score, combine_spread
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import Page, PairScore


def token_prefix(name: str) -> str | None:
    match = re.search(r"T\d+", name)
    return match.group(0) if match else None


def is_expected_pair(right_name: str, left_name: str, truth_tokens: set[str] | None) -> bool:
    right_token = token_prefix(right_name)
    left_token = token_prefix(left_name)
    if right_token is None or right_token != left_token:
        return False
    if truth_tokens is None:
        return True
    return right_token in truth_tokens


def score_pair(
    right_page: Page,
    left_page: Page,
    band_ratio: float,
    wide_ratio: float,
    max_offset: int,
    truth_tokens: set[str] | None = None,
) -> PairScore:
    expected = is_expected_pair(right_page.name, left_page.name, truth_tokens)
    seam_candidates: list[tuple[float, int, float, float, float, float, float]] = []

    for offset in range(-max_offset, max_offset + 1):
        strips = make_strips(left_page.gray, right_page.gray, band_ratio, offset)
        if strips is None:
            continue
        left, right = strips
        color = boundary_color_score(left, right)
        gradient = gradient_score(left, right)
        profile = row_profile_score(left, right)
        edge = edge_score(left, right)
        barrier = seam_barrier_score(left, right)
        seam_only = combine(color, gradient, profile, edge, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, barrier)
        seam_candidates.append((seam_only, offset, color, gradient, profile, edge, barrier))

    if not seam_candidates:
        return empty_score(right_page.name, left_page.name, expected)

    best: PairScore | None = None
    page_panel = max(page_panel_risk(left_page.gray), page_panel_risk(right_page.gray))
    for _, offset, color, gradient, profile, edge, barrier in sorted(seam_candidates, reverse=True)[:7]:
        wide = make_strips(left_page.gray, right_page.gray, wide_ratio, offset)
        if wide is None:
            continue
        left, right = wide
        ink = dark_ink_profile_score(left, right)
        energy = gradient_energy_balance_score(left, right)
        orientation = orientation_field_score(left, right)
        line = line_continuation_score(left, right)
        texture = texture_score(left, right)
        corr = profile_correlation_score(left, right)
        color_strips = make_color_strips(left_page.bgr, right_page.bgr, wide_ratio, offset)
        color_style = color_style_score(*color_strips) if color_strips is not None else 0.5
        panel = panel_boundary_penalty(left_page.gray, right_page.gray, offset)
        inner_gutter = inner_gutter_risk(left, right)
        composition = composition_spread_score(left_page.gray, right_page.gray, offset)
        seam_activity = seam_activity_score(left, right)
        seam_contact = seam_contact_score(left, right)
        patch = patch_ncc_score(left, right)
        total = combine(color, gradient, profile, edge, ink, energy, orientation, line, texture, corr, color_style, barrier)
        spread = combine_spread(
            total,
            color,
            gradient,
            profile,
            edge,
            ink,
            energy,
            orientation,
            line,
            texture,
            corr,
            color_style,
            panel,
            page_panel,
            inner_gutter,
            composition,
            seam_activity,
            seam_contact,
            patch,
            barrier,
        )
        review_score = combine_review_score(
            total,
            spread,
            color,
            gradient,
            profile,
            orientation,
            texture,
            color_style,
            page_panel,
            inner_gutter,
            composition,
            seam_activity,
            seam_contact,
            patch,
            barrier,
        )
        candidate = PairScore(
            right_page.name,
            left_page.name,
            total,
            spread,
            review_score,
            offset,
            color,
            gradient,
            profile,
            edge,
            ink,
            energy,
            orientation,
            line,
            texture,
            corr,
            color_style,
            panel,
            page_panel,
            inner_gutter,
            composition,
            seam_activity,
            seam_contact,
            patch,
            barrier,
            expected,
        )
        if best is None or candidate.spread > best.spread:
            best = candidate

    return best or empty_score(right_page.name, left_page.name, expected)


def empty_score(right_name: str, left_name: str, expected: bool) -> PairScore:
    return PairScore(
        right_name,
        left_name,
        0.0,
        0.0,
        0.0,
        0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        expected,
    )
