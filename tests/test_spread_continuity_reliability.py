from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from manga_pdf_to_epub.diagnosis.spread_continuity.lib.core.types import Page, PairScore
from manga_pdf_to_epub.diagnosis.spread_continuity.lib.scoring import reliability as reliability_module


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


def page(name: str, height: int = 900, width: int = 600) -> Page:
    gray = np.full((height, width), 128, dtype=np.uint8)
    bgr = np.repeat(gray[:, :, None], 3, axis=2)
    return Page(name, Path(f"{name}.png"), bgr, gray)


class SpreadContinuityReliabilityTests(unittest.TestCase):
    def test_reliability_probes_reuse_base_score_and_skip_unchanged_resize(self) -> None:
        right = page("page-001")
        left = page("page-002")
        calls: list[tuple[int, int]] = []

        def fake_score_pair(right_page, left_page, *_args, **_kwargs):
            calls.append((right_page.gray.shape[0], left_page.gray.shape[0]))
            return score(right_page.name, left_page.name, 0.61)

        with patch.object(reliability_module, "score_pair", fake_score_pair):
            signals = reliability_module.reliability_signals_for_candidates(
                [(right, left)],
                [score()],
                band_ratio=0.08,
                wide_ratio=0.20,
                max_offset=18,
                truth_tokens=None,
                workers=1,
                stability_threshold=0.47,
            )

        self.assertIn("page-001|page-002", signals)
        self.assertEqual([(800, 800)], calls)


if __name__ == "__main__":
    unittest.main()
