from __future__ import annotations

import csv
from pathlib import Path

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.outputs.scores import matching_row
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import Page, PairScore


MATCHING_FIELDS = [
    "right",
    "left",
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


def best_one_to_one_assignment(
    right_names: list[str],
    left_names: list[str],
    by_pair: dict[tuple[str, str], PairScore],
    min_spread: float = 0.0,
) -> list[PairScore]:
    n_right = len(right_names)
    memo: dict[tuple[int, int], tuple[float, list[PairScore]]] = {}

    def solve(i: int, used_mask: int) -> tuple[float, list[PairScore]]:
        key = (i, used_mask)
        if key in memo:
            return memo[key]
        if i == n_right:
            return 0.0, []

        best_score, best_items = solve(i + 1, used_mask)
        right = right_names[i]
        for j, left in enumerate(left_names):
            if used_mask & (1 << j):
                continue
            pair = by_pair.get((right, left))
            if pair is None or pair.spread < min_spread:
                continue
            rest_score, rest_items = solve(i + 1, used_mask | (1 << j))
            total = pair.spread + rest_score
            if total > best_score:
                best_score = total
                best_items = [pair] + rest_items
        memo[key] = (best_score, best_items)
        return memo[key]

    return solve(0, 0)[1]


def write_matching(
    scores: list[PairScore],
    right_pages: list[Page],
    left_pages: list[Page],
    output: Path,
    min_spread: float = 0.0,
) -> list[PairScore]:
    by_pair = {(score.right_name, score.left_name): score for score in scores}
    assignment = best_one_to_one_assignment(
        [page.name for page in right_pages],
        [page.name for page in left_pages],
        by_pair,
        min_spread=min_spread,
    )
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(MATCHING_FIELDS)
        for score in assignment:
            writer.writerow(matching_row(score))
    return assignment
