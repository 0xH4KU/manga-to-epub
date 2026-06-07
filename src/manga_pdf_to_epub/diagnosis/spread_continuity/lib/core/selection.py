from __future__ import annotations

import re

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import PairScore


def page_number(name: str) -> int | None:
    numbers = re.findall(r"\d+", name)
    return int(numbers[-1]) if numbers else None


def is_blank_composition_case(score: PairScore) -> bool:
    return score.barrier > 0.72 and max(score.seam_activity, score.seam_contact) < 0.30


def is_auto_safe_candidate(score: PairScore) -> bool:
    if is_blank_composition_case(score):
        return False
    if score.local_margin < 0.04:
        return False
    if weak_seam_structure_case(score):
        return False
    seam_support = max(score.seam_activity, score.seam_contact)
    return seam_support >= 0.45 or score.barrier < 0.45


def weak_seam_structure_case(score: PairScore) -> bool:
    seam_support = max(score.seam_activity, score.seam_contact)
    weak_profiles = min(score.profile, score.edge, score.ink) < 0.18
    weak_patch = score.patch < 0.70
    return seam_support > 0.70 and weak_profiles and weak_patch


def adjacent_candidate_items(
    scores: list[PairScore],
    threshold: float,
    review_threshold: float | None = None,
) -> list[tuple[int, int, PairScore]]:
    review_floor = threshold if review_threshold is None else review_threshold
    indexed: list[tuple[int, int, PairScore]] = []
    for score in scores:
        right_num = page_number(score.right_name)
        left_num = page_number(score.left_name)
        if right_num is None or left_num is None or abs(right_num - left_num) != 1:
            continue
        start = min(right_num, left_num)
        if score.spread < threshold and score.review_score < review_floor:
            continue
        indexed.append((start, start + 1, score))

    indexed.sort(key=lambda item: item[0])
    return indexed


def adjacent_candidate_items_with_edge_review_floor(
    scores: list[PairScore],
    threshold: float,
    review_threshold: float,
    edge_window: int = 3,
    book_page_count: int | None = None,
) -> list[tuple[int, int, PairScore]]:
    numbered: list[tuple[int, int, PairScore]] = []
    for score in scores:
        right_num = page_number(score.right_name)
        left_num = page_number(score.left_name)
        if right_num is None or left_num is None or abs(right_num - left_num) != 1:
            continue
        start = min(right_num, left_num)
        end = max(right_num, left_num)
        numbered.append((start, end, score))

    indexed: list[tuple[int, int, PairScore]] = []
    for start, end, score in numbered:
        near_book_end = book_page_count is not None and end >= book_page_count - edge_window + 1
        near_book_edge = start <= edge_window or near_book_end
        if score.spread >= threshold or (near_book_edge and score.review_score >= review_threshold):
            indexed.append((start, end, score))

    indexed.sort(key=lambda item: item[0])
    return indexed


def adjacent_candidate_clusters(
    scores: list[PairScore],
    threshold: float,
    review_threshold: float | None = None,
) -> list[list[tuple[int, int, PairScore]]]:
    indexed = adjacent_candidate_items(scores, threshold, review_threshold)
    return adjacent_candidate_clusters_from_items(indexed)


def adjacent_candidate_clusters_with_edge_review_floor(
    scores: list[PairScore],
    threshold: float,
    review_threshold: float,
    edge_window: int = 3,
    book_page_count: int | None = None,
) -> list[list[tuple[int, int, PairScore]]]:
    indexed = adjacent_candidate_items_with_edge_review_floor(
        scores,
        threshold,
        review_threshold,
        edge_window,
        book_page_count,
    )
    return adjacent_candidate_clusters_from_items(indexed)


def adjacent_candidate_clusters_from_items(
    indexed: list[tuple[int, int, PairScore]],
) -> list[list[tuple[int, int, PairScore]]]:
    clusters: list[list[tuple[int, int, PairScore]]] = []
    i = 0
    while i < len(indexed):
        start, end, score = indexed[i]
        cluster = [(start, end, score)]
        j = i + 1
        while j < len(indexed) and indexed[j][0] <= end:
            cluster.append(indexed[j])
            end = max(end, indexed[j][1])
            j += 1
        clusters.append(cluster)
        i = j
    return clusters


def select_non_overlapping_adjacent(
    scores: list[PairScore],
    threshold: float,
    min_margin: float = 0.04,
) -> list[PairScore]:
    selected: list[PairScore] = []
    for cluster in adjacent_candidate_clusters(scores, threshold):
        ranked = sorted(cluster, key=lambda item: (item[2].spread, item[2].review_score), reverse=True)
        winner = ranked[0][2]
        runner_up = ranked[1][2] if len(ranked) > 1 else None
        margin = winner.spread - (runner_up.spread if runner_up is not None else 0.0)
        if winner.spread >= threshold and margin >= min_margin and is_auto_safe_candidate(winner):
            selected.append(winner)
    return selected
