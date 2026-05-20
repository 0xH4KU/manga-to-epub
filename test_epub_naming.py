import unittest
from pathlib import Path

from epub_naming import generated_volume_title, infer_volume_number, safe_filename


class EpubNamingTests(unittest.TestCase):
    def test_infer_volume_number_uses_volume_token_trailing_number_or_fallback(self):
        self.assertEqual(7, infer_volume_number(Path("Series Vol.07.pdf")))
        self.assertEqual(12, infer_volume_number(Path("Series volume 12.pdf")))
        self.assertEqual(3, infer_volume_number(Path("Series 003.pdf")))
        self.assertEqual(5, infer_volume_number(Path("Series Special.pdf"), fallback=5))

    def test_generated_volume_title_uses_two_digit_volume_format(self):
        self.assertEqual("Series Vol.07", generated_volume_title("Series", 7))
        self.assertEqual("Series Vol.123", generated_volume_title("Series", 123))

    def test_safe_filename_replaces_invalid_characters_and_collapses_spaces(self):
        self.assertEqual("Series _ 01", safe_filename('Series / 01'))
        self.assertEqual("A_B_C", safe_filename('A:B*C'))
        self.assertEqual("Untitled", safe_filename('   '))


if __name__ == "__main__":
    unittest.main()
