import tempfile
import unittest
from pathlib import Path

from manga_pdf_to_epub.gui.layout_diagnosis import (
    read_insert_candidates_csv,
    read_spread_candidates_csv,
    reviewable_insert_candidates,
)


class DiagnosisCsvTests(unittest.TestCase):
    def test_reads_spread_candidates_from_adjacent_clusters_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "adjacent_clusters.csv"
            path.write_text(
                "\n".join(
                    [
                        "cluster,rank_in_cluster,decision,start_page,end_page,right,left,spread,review_score,raw_spread,raw_review_score,margin_to_next,local_margin,context_penalty,stability_score,relative_score,reliability_penalty,reliability_boost,composition,patch,seam_activity,seam_contact,barrier,page_panel,inner_gutter",
                        "1,1,review,37,38,page-037,page-038,0.910000,0.880000,0.900000,0.870000,0.100000,0.060000,0.000000,1.000000,0.900000,0.000000,0.020000,0.700000,0.800000,0.500000,0.520000,0.200000,0.300000,0.100000",
                        "2,1,auto,115,116,page-115,page-116,0.930000,0.910000,0.920000,0.900000,0.120000,0.080000,0.000000,1.000000,0.920000,0.000000,0.010000,0.720000,0.830000,0.550000,0.560000,0.210000,0.310000,0.110000",
                    ]
                ),
                encoding="utf-8",
            )

            candidates = read_spread_candidates_csv(path)

        self.assertEqual(["115-116", "037-038"], [item.pair_id for item in candidates])
        self.assertEqual(115, candidates[0].start_page)
        self.assertEqual("auto", candidates[0].decision)
        self.assertEqual(0.93, candidates[0].score)

    def test_reads_insert_candidates_from_gaps_csv_and_filters_reviewable_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gaps.csv"
            path.write_text(
                "\n".join(
                    [
                        "gap,after_page,before_page,safe_insert_score,label,visual_difference,continuity_risk,reasons",
                        "034-035,34,35,0.940000,C scene_change,0.700000,0.200000,dark pause page; visual discontinuity",
                        "037-038,37,38,0.110000,F do_not_insert,0.100000,0.900000,high continuity risk",
                    ]
                ),
                encoding="utf-8",
            )

            candidates = read_insert_candidates_csv(path)
            reviewable = reviewable_insert_candidates(candidates)

        self.assertEqual([34, 37], [item.after_page for item in candidates])
        self.assertEqual(["034-035"], [item.gap_id for item in reviewable])
        self.assertEqual(("dark pause page", "visual discontinuity"), reviewable[0].reasons)

    def test_insert_candidate_gap_id_is_derived_from_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gaps.csv"
            path.write_text(
                "\n".join(
                    [
                        "gap,after_page,before_page,safe_insert_score,label,visual_difference,continuity_risk,reasons",
                        "999-1000,34,35,0.940000,C scene_change,0.700000,0.200000,dark pause page",
                    ]
                ),
                encoding="utf-8",
            )

            candidates = read_insert_candidates_csv(path)

        self.assertEqual("034-035", candidates[0].gap_id)

    def test_missing_required_csv_columns_raise_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("start_page,end_page\n37,38\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                read_spread_candidates_csv(path)


if __name__ == "__main__":
    unittest.main()
