from __future__ import annotations

import csv
from pathlib import Path

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import PairScore


SCORE_FIELDS = [
    "total",
    "spread",
    "review_score",
    "raw_spread",
    "raw_review_score",
    "local_margin",
    "context_penalty",
    "context_boost",
    "stability_score",
    "relative_score",
    "reliability_penalty",
    "reliability_boost",
    "right",
    "left",
    "expected",
    "offset",
    "color",
    "gradient",
    "profile",
    "edge",
    "ink",
    "energy",
    "orientation",
    "line",
    "texture",
    "corr",
    "color_style",
    "panel",
    "page_panel",
    "inner_gutter",
    "composition",
    "seam_activity",
    "seam_contact",
    "patch",
    "barrier",
]


def write_scores(scores: list[PairScore], output: Path) -> None:
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", *SCORE_FIELDS])
        for rank, score in enumerate(scores, 1):
            writer.writerow(score_row(score, rank))


def score_row(score: PairScore, rank: int | None = None) -> list[object]:
    row = [
        f"{score.total:.6f}",
        f"{score.spread:.6f}",
        f"{score.review_score:.6f}",
        f"{score.raw_spread:.6f}",
        f"{score.raw_review_score:.6f}",
        f"{score.local_margin:.6f}",
        f"{score.context_penalty:.6f}",
        f"{score.context_boost:.6f}",
        f"{score.stability_score:.6f}",
        f"{score.relative_score:.6f}",
        f"{score.reliability_penalty:.6f}",
        f"{score.reliability_boost:.6f}",
        score.right_name,
        score.left_name,
        "yes" if score.expected else "no",
        score.offset,
        f"{score.color:.6f}",
        f"{score.gradient:.6f}",
        f"{score.profile:.6f}",
        f"{score.edge:.6f}",
        f"{score.ink:.6f}",
        f"{score.energy:.6f}",
        f"{score.orientation:.6f}",
        f"{score.line:.6f}",
        f"{score.texture:.6f}",
        f"{score.corr:.6f}",
        f"{score.color_style:.6f}",
        f"{score.panel:.6f}",
        f"{score.page_panel:.6f}",
        f"{score.inner_gutter:.6f}",
        f"{score.composition:.6f}",
        f"{score.seam_activity:.6f}",
        f"{score.seam_contact:.6f}",
        f"{score.patch:.6f}",
        f"{score.barrier:.6f}",
    ]
    return ([rank] if rank is not None else []) + row


def matching_row(score: PairScore) -> list[object]:
    return [
        score.right_name,
        score.left_name,
        f"{score.total:.6f}",
        f"{score.spread:.6f}",
        f"{score.review_score:.6f}",
        f"{score.raw_spread:.6f}",
        f"{score.raw_review_score:.6f}",
        f"{score.local_margin:.6f}",
        f"{score.context_penalty:.6f}",
        f"{score.context_boost:.6f}",
        f"{score.stability_score:.6f}",
        f"{score.relative_score:.6f}",
        f"{score.reliability_penalty:.6f}",
        f"{score.reliability_boost:.6f}",
        "yes" if score.expected else "no",
        score.offset,
        f"{score.color:.6f}",
        f"{score.gradient:.6f}",
        f"{score.profile:.6f}",
        f"{score.edge:.6f}",
        f"{score.ink:.6f}",
        f"{score.energy:.6f}",
        f"{score.orientation:.6f}",
        f"{score.line:.6f}",
        f"{score.texture:.6f}",
        f"{score.corr:.6f}",
        f"{score.color_style:.6f}",
        f"{score.panel:.6f}",
        f"{score.page_panel:.6f}",
        f"{score.inner_gutter:.6f}",
        f"{score.composition:.6f}",
        f"{score.seam_activity:.6f}",
        f"{score.seam_contact:.6f}",
        f"{score.patch:.6f}",
        f"{score.barrier:.6f}",
    ]
