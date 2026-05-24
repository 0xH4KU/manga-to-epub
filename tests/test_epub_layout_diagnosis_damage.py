import unittest
from types import SimpleNamespace

from manga_pdf_to_epub.gui.layout_diagnosis import (
    SpreadCandidate,
    diagnose_spread_damage,
    source_preview_placements,
)


def page(source_index: int):
    return SimpleNamespace(label=f"Page {source_index}", source_index=source_index, is_blank=False)


def blank(label: str = "Blank"):
    return SimpleNamespace(label=label, source_index=None, is_blank=True)


class SpreadDamageTests(unittest.TestCase):
    def test_source_preview_placements_include_virtual_apple_cover_gap(self):
        placements = source_preview_placements([page(1), page(2), page(3)], uses_apple_cover_gap=True)

        self.assertEqual(0, placements[1].preview_index)
        self.assertEqual(2, placements[2].preview_index)
        self.assertEqual(3, placements[3].preview_index)

    def test_spread_is_intact_without_virtual_cover_gap(self):
        spread = SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")
        entries = [page(index) for index in range(1, 41)]

        [damage] = diagnose_spread_damage(entries, [spread], uses_apple_cover_gap=False)

        self.assertEqual("intact", damage.status)
        self.assertEqual("037-038", damage.pair_id)

    def test_virtual_cover_gap_can_damage_otherwise_adjacent_spread(self):
        spread = SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")
        entries = [page(index) for index in range(1, 41)]

        [damage] = diagnose_spread_damage(entries, [spread], uses_apple_cover_gap=True)

        self.assertEqual("damaged", damage.status)
        self.assertIn("different preview spreads", damage.reason)

    def test_inserted_blank_before_first_page_can_repair_cover_gap_damage(self):
        spread = SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")
        entries = [page(index) for index in range(1, 37)] + [blank()] + [page(index) for index in range(37, 41)]

        [damage] = diagnose_spread_damage(entries, [spread], uses_apple_cover_gap=True)

        self.assertEqual("intact", damage.status)

    def test_missing_source_page_reports_missing_instead_of_damaged(self):
        spread = SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")
        entries = [page(index) for index in range(1, 38)]

        [damage] = diagnose_spread_damage(entries, [spread], uses_apple_cover_gap=True)

        self.assertEqual("missing", damage.status)
        self.assertIn("Page 38", damage.reason)

    def test_reversed_source_order_is_damaged(self):
        spread = SpreadCandidate("037-038", 37, 38, 1.0, 1.0, "manual")
        entries = [page(index) for index in range(1, 37)] + [page(38), page(37), page(39)]

        [damage] = diagnose_spread_damage(entries, [spread], uses_apple_cover_gap=False)

        self.assertEqual("damaged", damage.status)
        self.assertIn("wrong order", damage.reason)


if __name__ == "__main__":
    unittest.main()
