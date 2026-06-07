from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.reliability import ReliabilitySignals
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import Page, PairScore
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.scoring import jobs as scoring_jobs
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.scoring import reliability as reliability_module


def page(name: str) -> Page:
    gray = np.full((16, 16), 128, dtype=np.uint8)
    bgr = np.repeat(gray[:, :, None], 3, axis=2)
    return Page(name, Path(f"{name}.png"), bgr, gray)


def score(right: str = "page-001", left: str = "page-002", spread: float = 0.62) -> PairScore:
    return PairScore(
        right_name=right,
        left_name=left,
        total=spread,
        spread=spread,
        review_score=spread,
        offset=0,
        color=0.5,
        gradient=0.5,
        profile=0.5,
        edge=0.5,
        ink=0.5,
        energy=0.5,
        orientation=0.5,
        line=0.5,
        texture=0.5,
        corr=0.5,
        color_style=0.5,
        panel=0.0,
        page_panel=0.0,
        inner_gutter=0.0,
        composition=0.0,
        seam_activity=0.6,
        seam_contact=0.6,
        patch=0.6,
        barrier=0.0,
        expected=False,
    )


class SpreadContinuityProgressTests(unittest.TestCase):
    def test_score_candidate_pairs_reports_each_completed_pair(self) -> None:
        right = page("page-001")
        left = page("page-002")
        events = []

        with patch.object(scoring_jobs, "score_pair_job", return_value=score()) as score_job:
            scores = scoring_jobs.score_candidate_pairs(
                [(right, left)],
                band_ratio=0.08,
                wide_ratio=0.20,
                max_offset=18,
                truth_tokens=None,
                workers=1,
                progress_callback=events.append,
            )

        self.assertEqual(scores, events)
        score_job.assert_called_once()

    def test_reliability_signals_reports_each_completed_probe(self) -> None:
        right = page("page-001")
        left = page("page-002")
        signals = ReliabilitySignals(stability=0.9)
        events = []

        with patch.object(reliability_module, "reliability_probe_job", return_value=("page-001|page-002", signals)):
            result = reliability_module.reliability_signals_for_candidates(
                [(right, left)],
                [score()],
                band_ratio=0.08,
                wide_ratio=0.20,
                max_offset=18,
                truth_tokens=None,
                workers=1,
                stability_threshold=0.47,
                progress_callback=events.append,
            )

        self.assertEqual({"page-001|page-002": signals}, result)
        self.assertEqual([("page-001|page-002", signals)], events)
