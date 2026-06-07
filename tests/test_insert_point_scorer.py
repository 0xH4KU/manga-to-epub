from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from manga_pdf_to_epub.diagnosis.insert_point_scorer.features import PageFeatures, extract_page_features, visual_difference
from manga_pdf_to_epub.diagnosis.insert_point_scorer.report import write_features_csv, write_gaps_csv, write_html_report
from manga_pdf_to_epub.diagnosis.insert_point_scorer.scoring import GapScore, score_gap


def white_page() -> Image.Image:
    return Image.new("RGB", (120, 180), "white")


def dense_page() -> Image.Image:
    image = Image.new("RGB", (120, 180), "white")
    draw = ImageDraw.Draw(image)
    for y in range(4, 176, 8):
        draw.rectangle((4, y, 116, y + 4), fill="black")
    for x in range(8, 116, 18):
        draw.line((x, 0, x, 179), fill="black", width=2)
    return image


def title_page() -> Image.Image:
    image = Image.new("RGB", (120, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((36, 62, 84, 74), fill="black")
    draw.rectangle((42, 86, 78, 96), fill="black")
    return image


def features(
    page: int,
    *,
    ink: float = 0.3,
    edge: float = 0.3,
    blank: float = 0.2,
    dark: float = 0.05,
    title: float = 0.0,
    center: float | None = None,
    border: float | None = None,
    bottom: float | None = None,
) -> PageFeatures:
    return PageFeatures(
        page=page,
        width=100,
        height=150,
        ink_ratio=ink,
        edge_density=edge,
        blank_ratio=blank,
        dark_ratio=dark,
        title_likeness=title,
        content_density=(ink + edge) / 2,
        center_ink_ratio=ink if center is None else center,
        border_ink_ratio=ink if border is None else border,
        bottom_activity=edge if bottom is None else bottom,
    )


def report_feature(page: int) -> PageFeatures:
    return PageFeatures(
        page=page,
        width=100,
        height=150,
        ink_ratio=0.1,
        edge_density=0.2,
        blank_ratio=0.7,
        dark_ratio=0.02,
        title_likeness=0.5,
        content_density=0.15,
        center_ink_ratio=0.2,
        border_ink_ratio=0.04,
        bottom_activity=0.1,
    )


def report_gap() -> GapScore:
    return GapScore(
        gap_after_page=1,
        gap_before_page=2,
        safe_insert_score=0.82,
        label="A chapter_boundary",
        visual_difference=0.62,
        continuity_risk=0.2,
        reasons=("title-like page", "visual discontinuity"),
    )


class InsertPointFeatureTests(unittest.TestCase):
    def test_blank_page_has_high_blank_ratio_and_low_density(self) -> None:
        page_features = extract_page_features(1, white_page())

        self.assertGreater(page_features.blank_ratio, 0.95)
        self.assertLess(page_features.content_density, 0.05)
        self.assertLess(page_features.edge_density, 0.05)

    def test_dense_page_has_high_ink_and_edge_density(self) -> None:
        page_features = extract_page_features(2, dense_page())

        self.assertGreater(page_features.ink_ratio, 0.35)
        self.assertGreater(page_features.edge_density, 0.2)
        self.assertGreater(page_features.content_density, 0.25)

    def test_sparse_centered_page_is_title_like(self) -> None:
        page_features = extract_page_features(3, title_page())

        self.assertGreater(page_features.title_likeness, 0.6)
        self.assertGreater(page_features.center_ink_ratio, page_features.border_ink_ratio)
        self.assertGreater(page_features.blank_ratio, 0.7)

    def test_visual_difference_tracks_page_change(self) -> None:
        same = visual_difference(extract_page_features(1, white_page()), extract_page_features(2, white_page()))
        changed = visual_difference(extract_page_features(1, white_page()), extract_page_features(2, dense_page()))

        self.assertLess(same, 0.05)
        self.assertGreater(changed, 0.35)


class InsertPointScoringTests(unittest.TestCase):
    def test_low_content_gap_gets_safe_pause_label(self) -> None:
        gap = score_gap(
            left=features(10, ink=0.08, edge=0.07, blank=0.82),
            right=features(11, ink=0.12, edge=0.09, blank=0.76),
            previous=features(9, ink=0.35, edge=0.33, blank=0.2),
            next_page=features(12, ink=0.36, edge=0.34, blank=0.18),
            visual_difference=0.55,
            left_continuity=0.25,
            right_continuity=0.28,
        )

        self.assertEqual("B low_content_pause", gap.label)
        self.assertGreaterEqual(gap.safe_insert_score, 0.72)
        self.assertIn("low content", gap.reasons)

    def test_dense_continuous_gap_is_do_not_insert(self) -> None:
        gap = score_gap(
            left=features(20, ink=0.62, edge=0.7, blank=0.05),
            right=features(21, ink=0.64, edge=0.68, blank=0.04),
            previous=features(19, ink=0.6, edge=0.66, blank=0.05),
            next_page=features(22, ink=0.61, edge=0.67, blank=0.05),
            visual_difference=0.08,
            left_continuity=0.88,
            right_continuity=0.86,
        )

        self.assertEqual("F do_not_insert", gap.label)
        self.assertLessEqual(gap.safe_insert_score, 0.25)
        self.assertIn("high continuity risk", gap.reasons)

    def test_title_like_page_gets_chapter_boundary_label(self) -> None:
        gap = score_gap(
            left=features(30, ink=0.09, edge=0.12, blank=0.78, title=0.9),
            right=features(31, ink=0.42, edge=0.38, blank=0.18),
            previous=features(29, ink=0.31, edge=0.29, blank=0.22),
            next_page=features(32, ink=0.44, edge=0.41, blank=0.15),
            visual_difference=0.72,
            left_continuity=0.2,
            right_continuity=0.62,
        )

        self.assertEqual("A chapter_boundary", gap.label)
        self.assertGreaterEqual(gap.safe_insert_score, 0.82)
        self.assertIn("title-like page", gap.reasons)


class InsertPointReportTests(unittest.TestCase):
    def test_write_features_csv_has_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "features.csv"

            write_features_csv([report_feature(1)], path)

            with path.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual("1", rows[0]["page"])
            self.assertEqual("0.700000", rows[0]["blank_ratio"])
            self.assertEqual("0.500000", rows[0]["title_likeness"])

    def test_write_gaps_csv_has_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gaps.csv"

            write_gaps_csv([report_gap()], path)

            with path.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual("001-002", rows[0]["gap"])
            self.assertEqual("A chapter_boundary", rows[0]["label"])
            self.assertEqual("title-like page; visual discontinuity", rows[0]["reasons"])

    def test_html_report_escapes_title_and_includes_thumbnails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"

            write_html_report(
                [report_gap()],
                path,
                title='Mgf <01> & "test"',
                thumbs_dir_name="thumbs",
                page_count=2,
            )

            html = path.read_text(encoding="utf-8")
            self.assertIn("Mgf &lt;01&gt; &amp; &quot;test&quot;", html)
            self.assertIn("thumbs/page-0001.jpg", html)
            self.assertIn("thumbs/page-0002.jpg", html)


if __name__ == "__main__":
    unittest.main()
