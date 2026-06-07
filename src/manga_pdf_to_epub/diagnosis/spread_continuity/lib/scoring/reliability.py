from __future__ import annotations

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.image_io import resize_page
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.scoring.pair_scoring import score_pair
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.reliability import (
    ReliabilitySignals,
    make_trimmed_page,
    stability_from_scores,
)
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import Page, PairScore


def reliability_probe_for_pair(
    right: Page,
    left: Page,
    band_ratio: float,
    wide_ratio: float,
    max_offset: int,
    truth_tokens: set[str] | None,
    base_spread: float | None = None,
) -> ReliabilitySignals:
    if base_spread is None:
        candidates = [score_pair(right, left, band_ratio, wide_ratio, max_offset, truth_tokens).spread]
    else:
        candidates = [base_spread]
    for probe_height in (800, 1200):
        resized_right = resize_page(right, probe_height)
        resized_left = resize_page(left, probe_height)
        if resized_right is right and resized_left is left:
            continue
        candidates.append(score_pair(resized_right, resized_left, band_ratio, wide_ratio, max_offset, truth_tokens).spread)

    trimmed_right = make_trimmed_page(right, Page)
    trimmed_left = make_trimmed_page(left, Page)
    if trimmed_right is not right or trimmed_left is not left:
        candidates.append(score_pair(trimmed_right, trimmed_left, band_ratio, wide_ratio, max_offset, truth_tokens).spread)

    return ReliabilitySignals(stability=stability_from_scores(candidates))


def reliability_probe_job(
    job: tuple[Page, Page, float, float, int, set[str] | None, float],
) -> tuple[str, ReliabilitySignals]:
    right, left, band_ratio, wide_ratio, max_offset, truth_tokens, base_spread = job
    key = f"{right.name}|{left.name}"
    return key, reliability_probe_for_pair(
        right,
        left,
        band_ratio,
        wide_ratio,
        max_offset,
        truth_tokens,
        base_spread,
    )


def reliability_signals_for_candidates(
    candidate_pairs: list[tuple[Page, Page]],
    scores: list[PairScore],
    band_ratio: float,
    wide_ratio: float,
    max_offset: int,
    truth_tokens: set[str] | None,
    workers: int,
    stability_threshold: float,
) -> dict[str, ReliabilitySignals]:
    pages_by_pair = {(right.name, left.name): (right, left) for right, left in candidate_pairs}
    jobs = []
    for score in scores:
        if max(score.spread, score.review_score) < stability_threshold:
            continue
        pages = pages_by_pair.get((score.right_name, score.left_name))
        if pages is None:
            continue
        right, left = pages
        jobs.append((right, left, band_ratio, wide_ratio, max_offset, truth_tokens, score.spread))

    if not jobs:
        return {}
    if workers <= 1 or len(jobs) <= 1:
        return dict(reliability_probe_job(job) for job in jobs)

    from multiprocessing import get_context

    with get_context("spawn").Pool(processes=workers) as pool:
        return dict(pool.imap(reliability_probe_job, jobs))
