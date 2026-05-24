import unittest
from types import SimpleNamespace

from manga_pdf_to_epub.gui.layout_diagnosis import (
    InsertCandidate,
    SpreadCandidate,
    classify_insert_points,
)


def page(source_index: int):
    return SimpleNamespace(label=f"Page {source_index}", source_index=source_index, is_blank=False)


class InsertSuggestionTests(unittest.TestCase):
    def test_high_scoring_gap_before_damaged_spread_is_suggested(self):
        entries = [page(index) for index in range(1, 41)]
        confirmed = [SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")]
        insert_candidates = [
            InsertCandidate("034-035", 34, 35, 0.94, "C scene_change", 0.7, 0.2, ("scene change",)),
            InsertCandidate("037-038", 37, 38, 0.99, "B low_content_pause", 0.8, 0.1, ("low content",)),
        ]

        result = classify_insert_points(entries, confirmed, insert_candidates, uses_apple_cover_gap=True)

        self.assertEqual([34], [item.after_page for item in result.suggestions])
        self.assertEqual(34, result.suggestions[0].insertion_index)
        self.assertEqual(33, result.suggestions[0].marker_entry_index)
        self.assertEqual(("037-038",), result.suggestions[0].fixes)

    def test_gap_inside_confirmed_spread_is_protected_even_with_high_score(self):
        entries = [page(index) for index in range(1, 41)]
        confirmed = [SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")]
        insert_candidates = [
            InsertCandidate("037-038", 37, 38, 0.99, "B low_content_pause", 0.8, 0.1, ("low content",)),
        ]

        result = classify_insert_points(entries, confirmed, insert_candidates, uses_apple_cover_gap=True)

        self.assertEqual([], result.suggestions)
        self.assertEqual([37], [item.after_page for item in result.protected])
        self.assertIn("inside confirmed spread", result.protected[0].reason)

    def test_candidate_that_breaks_currently_intact_spread_is_protected(self):
        entries = [page(index) for index in range(1, 8)]
        confirmed = [SpreadCandidate("003-004", 3, 4, 1.0, 1.0, "manual")]
        insert_candidates = [
            InsertCandidate("001-002", 1, 2, 0.91, "C scene_change", 0.7, 0.2, ("scene change",)),
        ]

        result = classify_insert_points(entries, confirmed, insert_candidates, uses_apple_cover_gap=False)

        self.assertEqual([], result.suggestions)
        self.assertEqual(1, len(result.protected))
        self.assertEqual("protected", result.protected[0].kind)
        self.assertIn("003-004", result.protected[0].reason)

    def test_stale_candidate_with_missing_source_page_is_ignored(self):
        entries = [page(index) for index in range(1, 6)]
        confirmed = [SpreadCandidate("003-004", 3, 4, 1.0, 1.0, "manual")]
        insert_candidates = [
            InsertCandidate("009-010", 9, 10, 0.80, "C scene_change", 0.7, 0.2, ("scene change",)),
        ]

        result = classify_insert_points(entries, confirmed, insert_candidates, uses_apple_cover_gap=False)

        self.assertEqual([], result.suggestions)
        self.assertEqual([], result.protected)
        self.assertEqual(["009-010"], result.stale_gap_ids)

    def test_stale_candidate_with_separated_source_pages_is_ignored(self):
        entries = [page(1), page(2), page(99), page(3), page(4), page(5)]
        confirmed = [SpreadCandidate("003-004", 3, 4, 1.0, 1.0, "manual")]
        insert_candidates = [
            InsertCandidate("002-003", 2, 3, 0.80, "C scene_change", 0.7, 0.2, ("scene change",)),
        ]

        result = classify_insert_points(entries, confirmed, insert_candidates, uses_apple_cover_gap=False)

        self.assertEqual([], result.suggestions)
        self.assertEqual([], result.protected)
        self.assertEqual(["002-003"], result.stale_gap_ids)


if __name__ == "__main__":
    unittest.main()
