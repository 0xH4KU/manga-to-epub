import unittest
from unittest.mock import patch

from manga_pdf_to_epub import fitz_compat
from manga_pdf_to_epub.pdf.image_types import PdfImageError


class FitzCompatTests(unittest.TestCase):
    def test_missing_pymupdf_error_mentions_install_command(self):
        with patch("manga_pdf_to_epub.fitz_compat.importlib.import_module", side_effect=ModuleNotFoundError("fitz")):
            with self.assertRaisesRegex(PdfImageError, r"\.venv/bin/python -m pip install -r requirements\.txt"):
                fitz_compat.load_fitz()


if __name__ == "__main__":
    unittest.main()
