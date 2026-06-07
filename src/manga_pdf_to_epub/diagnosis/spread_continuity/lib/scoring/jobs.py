from __future__ import annotations

from collections.abc import Callable

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.scoring.pair_scoring import score_pair
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import Page, PairScore


def score_pair_job(
    job: tuple[Page, Page, float, float, int, set[str] | None],
) -> PairScore:
    right, left, band_ratio, wide_ratio, max_offset, truth_tokens = job
    return score_pair(right, left, band_ratio, wide_ratio, max_offset, truth_tokens)


def score_candidate_pairs(
    candidate_pairs: list[tuple[Page, Page]],
    band_ratio: float,
    wide_ratio: float,
    max_offset: int,
    truth_tokens: set[str] | None,
    workers: int,
    progress_callback: Callable[[PairScore], None] | None = None,
) -> list[PairScore]:
    jobs = [(right, left, band_ratio, wide_ratio, max_offset, truth_tokens) for right, left in candidate_pairs]
    if workers <= 1 or len(jobs) <= 1:
        scores = []
        for job in jobs:
            score = score_pair_job(job)
            scores.append(score)
            if progress_callback is not None:
                progress_callback(score)
        return scores

    from multiprocessing import get_context

    with get_context("spawn").Pool(processes=workers) as pool:
        scores = []
        for score in pool.imap(score_pair_job, jobs):
            scores.append(score)
            if progress_callback is not None:
                progress_callback(score)
        return scores
