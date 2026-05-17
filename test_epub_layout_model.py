import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from epub_layout_model import LayoutModel
from test_pdf_to_cbz_lossless import _two_page_pdf_with_late_cover


class EpubLayoutModelTests(unittest.TestCase):
    def test_inserts_blank_page_at_arbitrary_position_and_exports_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)

            model.insert_blank(1)
            counts = model.export_epub(epub_path, overwrite=True, title="Comic")

            self.assertEqual({"jpg": 2, "png": 0, "blank": 1, "total": 3}, counts)
            self.assertEqual(["Page 1", "Blank 1", "Page 2"], [entry.label for entry in model.entries])
            with ZipFile(epub_path) as archive:
                names = archive.namelist()
                self.assertIn("EPUB/xhtml/blank-0001.xhtml", names)
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertLess(opf.index('idref="page-0001"'), opf.index('idref="blank-0001"'))
                self.assertLess(opf.index('idref="blank-0001"'), opf.index('idref="page-0002"'))

    def test_deletes_only_blank_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)

            model.insert_blank(0)
            model.delete_blank(0)

            self.assertEqual(["Page 1", "Page 2"], [entry.label for entry in model.entries])
            with self.assertRaises(ValueError):
                model.delete_blank(0)

    def test_delete_entry_can_remove_source_pages_and_export_without_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)

            model.delete_entry(1)
            counts = model.export_epub(epub_path, overwrite=True, title="Comic")

            self.assertEqual(["Page 1"], [entry.label for entry in model.entries])
            self.assertEqual({"jpg": 1, "png": 0, "total": 1}, counts)
            with ZipFile(epub_path) as archive:
                self.assertNotIn("EPUB/images/page-0002.jpg", archive.namelist())

    def test_saves_and_applies_blank_page_preset_to_another_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            other_pdf_path = Path(tmp) / "other.pdf"
            preset_path = Path(tmp) / "layout.json"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            other_pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)
            model.insert_blank(0)
            model.insert_blank(2)

            model.save_preset(preset_path)
            applied = LayoutModel.from_pdf(other_pdf_path)
            applied.apply_preset(preset_path)

            self.assertEqual(
                ["Blank 1", "Page 1", "Blank 2", "Page 2"],
                [entry.label for entry in applied.entries],
            )

    def test_preset_preserves_deleted_source_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            other_pdf_path = Path(tmp) / "other.pdf"
            preset_path = Path(tmp) / "layout.json"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            other_pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)
            model.delete_entry(1)
            model.insert_blank(1)

            model.save_preset(preset_path)
            applied = LayoutModel.from_pdf(other_pdf_path)
            applied.apply_preset(preset_path)

            self.assertEqual(["Page 1", "Blank 1"], [entry.label for entry in applied.entries])


if __name__ == "__main__":
    unittest.main()
