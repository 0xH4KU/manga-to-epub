from __future__ import annotations

import csv
from pathlib import Path

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.outputs.matching import MATCHING_FIELDS
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.outputs.scores import matching_row
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.selection import (
    adjacent_candidate_clusters_with_edge_review_floor,
    is_auto_safe_candidate,
    select_non_overlapping_adjacent,
)
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import PairScore


def write_review(scores: list[PairScore], output: Path, threshold: float) -> None:
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank",
                "right",
                "left",
                "spread",
                "total",
                "review_score",
                "raw_spread",
                "raw_review_score",
                "decision",
                "margin_to_next",
                "local_margin",
                "context_penalty",
                "stability_score",
                "relative_score",
                "reliability_penalty",
                "reliability_boost",
                "expected",
                "patch",
                "composition",
                "seam_activity",
                "panel",
                "page_panel",
                "inner_gutter",
                "barrier",
                "seam_contact",
            ]
        )
        for idx, score in enumerate(scores, 1):
            next_score = scores[idx].spread if idx < len(scores) else 0.0
            margin = score.spread - next_score
            if score.spread >= threshold and margin >= 0.08 and is_auto_safe_candidate(score):
                decision = "auto"
            elif score.spread >= threshold:
                decision = "review"
            elif score.review_score >= threshold:
                decision = "review"
            elif score.spread >= threshold - 0.06:
                decision = "borderline"
            elif score.review_score >= threshold - 0.04:
                decision = "borderline"
            else:
                decision = "reject"
            writer.writerow(
                [
                    idx,
                    score.right_name,
                    score.left_name,
                    f"{score.spread:.6f}",
                    f"{score.total:.6f}",
                    f"{score.review_score:.6f}",
                    f"{score.raw_spread:.6f}",
                    f"{score.raw_review_score:.6f}",
                    decision,
                    f"{margin:.6f}",
                    f"{score.local_margin:.6f}",
                    f"{score.context_penalty:.6f}",
                    f"{score.stability_score:.6f}",
                    f"{score.relative_score:.6f}",
                    f"{score.reliability_penalty:.6f}",
                    f"{score.reliability_boost:.6f}",
                    "yes" if score.expected else "no",
                    f"{score.patch:.6f}",
                    f"{score.composition:.6f}",
                    f"{score.seam_activity:.6f}",
                    f"{score.panel:.6f}",
                    f"{score.page_panel:.6f}",
                    f"{score.inner_gutter:.6f}",
                    f"{score.barrier:.6f}",
                    f"{score.seam_contact:.6f}",
                ]
            )


def write_selected(scores: list[PairScore], output: Path, threshold: float) -> list[PairScore]:
    selected = select_non_overlapping_adjacent(scores, threshold)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(MATCHING_FIELDS)
        for score in selected:
            writer.writerow(matching_row(score))
    return selected


def write_adjacent_clusters(
    scores: list[PairScore],
    output: Path,
    threshold: float,
    book_page_count: int | None = None,
) -> None:
    clusters = adjacent_candidate_clusters_with_edge_review_floor(
        scores,
        threshold,
        review_threshold=threshold - 0.01,
        book_page_count=book_page_count,
    )
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "cluster",
                "rank_in_cluster",
                "decision",
                "start_page",
                "end_page",
                "right",
                "left",
                "spread",
                "review_score",
                "raw_spread",
                "raw_review_score",
                "margin_to_next",
                "local_margin",
                "context_penalty",
                "stability_score",
                "relative_score",
                "reliability_penalty",
                "reliability_boost",
                "composition",
                "patch",
                "seam_activity",
                "seam_contact",
                "barrier",
                "page_panel",
                "inner_gutter",
            ]
        )
        for cluster_idx, cluster in enumerate(clusters, 1):
            ranked = sorted(cluster, key=lambda item: (item[2].spread, item[2].review_score), reverse=True)
            for rank, (start, end, score) in enumerate(ranked, 1):
                next_spread = ranked[rank][2].spread if rank < len(ranked) else 0.0
                margin = score.spread - next_spread
                if rank == 1 and score.spread >= threshold and margin >= 0.04 and is_auto_safe_candidate(score):
                    decision = "auto"
                else:
                    decision = "review"
                writer.writerow(
                    [
                        cluster_idx,
                        rank,
                        decision,
                        start,
                        end,
                        score.right_name,
                        score.left_name,
                        f"{score.spread:.6f}",
                        f"{score.review_score:.6f}",
                        f"{score.raw_spread:.6f}",
                        f"{score.raw_review_score:.6f}",
                        f"{margin:.6f}",
                        f"{score.local_margin:.6f}",
                        f"{score.context_penalty:.6f}",
                        f"{score.stability_score:.6f}",
                        f"{score.relative_score:.6f}",
                        f"{score.reliability_penalty:.6f}",
                        f"{score.reliability_boost:.6f}",
                        f"{score.composition:.6f}",
                        f"{score.patch:.6f}",
                        f"{score.seam_activity:.6f}",
                        f"{score.seam_contact:.6f}",
                        f"{score.barrier:.6f}",
                        f"{score.page_panel:.6f}",
                        f"{score.inner_gutter:.6f}",
                    ]
                )
