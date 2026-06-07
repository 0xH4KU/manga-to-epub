from __future__ import annotations

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.features.common import clamp01


def combine(
    color: float,
    gradient: float,
    profile: float,
    edge: float,
    ink: float,
    energy: float,
    orientation: float,
    line: float,
    texture: float,
    corr: float,
    color_style: float,
    barrier: float,
) -> float:
    positive = (
        0.13 * color
        + 0.15 * gradient
        + 0.13 * profile
        + 0.09 * edge
        + 0.12 * ink
        + 0.09 * energy
        + 0.07 * orientation
        + 0.10 * line
        + 0.04 * texture
        + 0.07 * corr
        + 0.06 * color_style
    )
    return clamp01(positive * (1.0 - 0.46 * barrier))


def combine_spread(
    total: float,
    color: float,
    gradient: float,
    profile: float,
    edge: float,
    ink: float,
    energy: float,
    orientation: float,
    line: float,
    texture: float,
    corr: float,
    color_style: float,
    panel: float,
    page_panel: float,
    inner_gutter: float,
    composition: float,
    seam_activity: float,
    seam_contact: float,
    patch: float,
    barrier: float,
) -> float:
    continuity = (
        0.16 * color
        + 0.16 * gradient
        + 0.14 * profile
        + 0.10 * edge
        + 0.10 * ink
        + 0.08 * energy
        + 0.08 * orientation
        + 0.09 * line
        + 0.04 * corr
        + 0.04 * color_style
    )
    evidence = 0.44 * continuity + 0.16 * total + 0.13 * seam_activity + 0.18 * patch + 0.09 * composition
    support = max(patch, seam_activity, seam_contact)
    composition_support = max(support, 0.86 * composition)
    effective_panel = panel * (1.0 - support)
    page_panel_penalty = page_panel * (1.0 - 0.55 * composition_support)
    gutter_penalty = inner_gutter * (1.0 - 0.70 * composition_support)
    barrier_penalty = barrier * (1.0 - 0.35 * composition_support)
    penalty = 0.24 * effective_panel + 0.24 * page_panel_penalty + 0.20 * gutter_penalty + 0.36 * barrier_penalty
    composition_gate = blank_composition_gate(barrier, inner_gutter, page_panel, seam_activity, seam_contact)
    composition_case = composition_gate * composition
    composition_case *= 0.74 + 0.18 * max(color, gradient, profile) + 0.08 * max(texture, corr, color_style)
    composition_case *= 1.0 - 0.10 * page_panel * max(0.0, 1.0 - composition)
    composition_case *= 1.0 - 0.08 * panel * max(0.0, 1.0 - seam_contact)
    return clamp01(max(evidence * (1.0 - penalty), composition_case))


def combine_review_score(
    total: float,
    spread: float,
    color: float,
    gradient: float,
    profile: float,
    orientation: float,
    texture: float,
    color_style: float,
    page_panel: float,
    inner_gutter: float,
    composition: float,
    seam_activity: float,
    seam_contact: float,
    patch: float,
    barrier: float,
) -> float:
    # Review score is intentionally permissive. It catches low-information spreads
    # such as cover/design spreads that are not safe to auto-accept.
    design_continuity = (
        0.18 * color
        + 0.18 * gradient
        + 0.18 * profile
        + 0.14 * orientation
        + 0.10 * texture
        + 0.10 * color_style
        + 0.12 * total
    )
    seam_support = 0.40 * patch + 0.34 * seam_activity + 0.13 * seam_contact + 0.13 * composition
    gutter_case = (
        inner_gutter
        * max(color, profile)
        * max(0.0, 1.0 - max(seam_activity, seam_contact))
        * (1.0 - 0.65 * page_panel)
    )
    composition_gate = blank_composition_gate(barrier, inner_gutter, page_panel, seam_activity, seam_contact)
    composition_case = composition_gate * composition * (0.76 + 0.16 * design_continuity + 0.08 * max(color, gradient, profile))
    score = 0.58 * design_continuity + 0.22 * seam_support + 0.12 * gutter_case
    multi_panel_gutter_risk = (
        page_panel
        * inner_gutter
        * max(0.0, 1.0 - seam_contact)
        * max(0.35, 1.0 - 0.50 * seam_activity)
    )
    penalized = max(spread, score) * (1.0 - 0.52 * multi_panel_gutter_risk) * (1.0 - 0.18 * barrier)
    return clamp01(max(penalized, composition_case * (1.0 - 0.18 * page_panel)))


def blank_composition_gate(
    barrier: float,
    inner_gutter: float,
    page_panel: float,
    seam_activity: float,
    seam_contact: float,
) -> float:
    barrier_gate = clamp01((barrier - 0.72) / 0.25)
    quiet_seam = clamp01((0.30 - max(seam_activity, seam_contact)) / 0.30)
    gutter_gate = clamp01((inner_gutter - 0.82) / 0.18) * quiet_seam * (1.0 - 0.55 * page_panel)
    return clamp01(max(barrier_gate, gutter_gate))
