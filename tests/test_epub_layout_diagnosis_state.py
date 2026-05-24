import unittest

from manga_pdf_to_epub.gui.layout_diagnosis import (
    DiagnosisSession,
    SpreadCandidate,
    adjacent_pair_id,
)


class DiagnosisStateTests(unittest.TestCase):
    def test_candidates_start_pending_and_true_candidates_drive_confirmed_set(self):
        session = DiagnosisSession(source_page_count=200)
        session.load_spread_candidates(
            [
                SpreadCandidate("037-038", 37, 38, 0.91, 0.88, "review"),
                SpreadCandidate("071-072", 71, 72, 0.74, 0.79, "review"),
            ]
        )

        self.assertEqual(2, session.pending_count())
        session.mark_candidate("037-038", "true")
        session.mark_candidate("071-072", "false")

        self.assertEqual(0, session.pending_count())
        self.assertEqual([(37, 38)], [(item.start_page, item.end_page) for item in session.confirmed_spreads()])

    def test_manual_spread_is_added_as_confirmed_candidate(self):
        session = DiagnosisSession(source_page_count=200)

        manual = session.add_manual_spread(173, 174)

        self.assertEqual("173-174", manual.pair_id)
        self.assertEqual("manual", manual.source)
        self.assertEqual([(173, 174)], [(item.start_page, item.end_page) for item in session.confirmed_spreads()])

    def test_pair_validation_requires_adjacent_pages_inside_source_count(self):
        session = DiagnosisSession(source_page_count=50)

        with self.assertRaisesRegex(ValueError, "adjacent"):
            session.add_manual_spread(10, 12)
        with self.assertRaisesRegex(ValueError, "source page range"):
            session.add_manual_spread(0, 1)
        with self.assertRaisesRegex(ValueError, "source page range"):
            session.add_manual_spread(50, 51)

    def test_pair_id_is_zero_padded_for_sorting_and_display(self):
        self.assertEqual("007-008", adjacent_pair_id(7, 8))


if __name__ == "__main__":
    unittest.main()
