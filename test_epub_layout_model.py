import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from epub_layout_model import LayoutModel
from test_pdf_to_cbz_lossless import _pdf_from_objects, _stream_object, _two_page_pdf_with_late_cover


def _four_page_pdf():
    draw = b"q 2 0 0 1 0 0 cm /Im0 Do Q"
    image_template = (
        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 1 "
        b"/BitsPerComponent 8 /ColorSpace /DeviceRGB /Filter /DCTDecode /Length __LEN__ >>"
    )
    return _pdf_from_objects(
        [
            (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
            (2, b"<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R 6 0 R] /Count 4 >>"),
            (
                3,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 11 0 R >> >> /Contents 7 0 R >>",
            ),
            (
                4,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 12 0 R >> >> /Contents 8 0 R >>",
            ),
            (
                5,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 13 0 R >> >> /Contents 9 0 R >>",
            ),
            (
                6,
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 1] "
                b"/Resources << /XObject << /Im0 14 0 R >> >> /Contents 10 0 R >>",
            ),
            (7, _stream_object(b"<< /Length __LEN__ >>", draw)),
            (8, _stream_object(b"<< /Length __LEN__ >>", draw)),
            (9, _stream_object(b"<< /Length __LEN__ >>", draw)),
            (10, _stream_object(b"<< /Length __LEN__ >>", draw)),
            (11, _stream_object(image_template, b"\xff\xd8PAGE1\xff\xd9")),
            (12, _stream_object(image_template, b"\xff\xd8PAGE2\xff\xd9")),
            (13, _stream_object(image_template, b"\xff\xd8PAGE3\xff\xd9")),
            (14, _stream_object(image_template, b"\xff\xd8PAGE4\xff\xd9")),
        ]
    )


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
                self.assertLess(opf.index('idref="blank-0001"'), opf.index('idref="page-0003"'))

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

    def test_delete_range_returns_entries_for_grouped_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(_four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)

            deleted = model.delete_range(1, 2)

            self.assertEqual(["Page 1", "Page 4"], [entry.label for entry in model.entries])
            self.assertEqual([(1, "Page 2"), (2, "Page 3")], [(index, entry.label) for index, entry in deleted])

    def test_quick_delete_helpers_reject_invalid_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)

            with self.assertRaises(ValueError):
                model.delete_first(0)
            with self.assertRaises(ValueError):
                model.delete_last(-1)
            with self.assertRaises(ValueError):
                model.delete_range(2, 1)

    def test_export_normalizes_deleted_source_page_to_sequential_epub_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)
            model.delete_first(3)

            model.export_epub(epub_path, overwrite=True, title="Comic")

            self.assertEqual(["Page 4"], [entry.label for entry in model.entries])
            with ZipFile(epub_path) as archive:
                names = archive.namelist()
                self.assertIn("EPUB/images/page-0001.jpg", names)
                self.assertNotIn("EPUB/images/page-0004.jpg", names)
                self.assertIn("EPUB/xhtml/page-0001.xhtml", names)
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                nav = archive.read("EPUB/nav.xhtml").decode("utf-8")
                self.assertIn('idref="page-0001"', opf)
                self.assertNotIn('idref="page-0004"', opf)
                self.assertIn("Page 4", nav)

    def test_model_exports_metadata_and_source_cover_after_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)
            model.title = "Volume & 1"
            model.author = "Author <Name>"
            model.language = "ja"
            model.set_cover(2)
            model.delete_first(1)

            model.export_epub(epub_path, overwrite=True)

            with ZipFile(epub_path) as archive:
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn("<dc:title>Volume &amp; 1</dc:title>", opf)
                self.assertIn("<dc:creator>Author &lt;Name&gt;</dc:creator>", opf)
                self.assertIn("<dc:language>ja</dc:language>", opf)
                self.assertIn('id="img-0001" href="images/page-0001.jpg" media-type="image/jpeg" properties="cover-image"', opf)

    def test_cover_falls_back_when_selected_page_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(_four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)
            model.set_cover(3)

            model.delete_range(2, 2)

            self.assertEqual(1, model.cover_source_index)

    def test_export_selected_images_skips_blanks_and_uses_spine_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            output_dir = Path(tmp) / "images"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)
            model.insert_blank(1)

            exported, skipped = model.export_selected_images([0, 1, 2], output_dir)

            self.assertEqual(["0001.jpg", "0003.jpg"], [path.name for path in exported])
            self.assertEqual(1, skipped)
            self.assertEqual(b"\xff\xd8COVER\xff\xd9", (output_dir / "0001.jpg").read_bytes())
            self.assertEqual(b"\xff\xd8PAGE2\xff\xd9", (output_dir / "0003.jpg").read_bytes())

    def test_insert_external_png_exports_as_epub_page_and_selected_image(self):
        png = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            image_path = Path(tmp) / "extra.png"
            epub_path = Path(tmp) / "comic.epub"
            output_dir = Path(tmp) / "selected"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            image_path.write_bytes(png)
            model = LayoutModel.from_pdf(pdf_path)

            model.insert_image(1, image_path)
            model.export_epub(epub_path, overwrite=True)
            exported, skipped = model.export_selected_images([1], output_dir)

            self.assertEqual(0, skipped)
            self.assertEqual(["0002.png"], [path.name for path in exported])
            self.assertEqual(png, (output_dir / "0002.png").read_bytes())
            with ZipFile(epub_path) as archive:
                self.assertEqual(png, archive.read("EPUB/images/page-0002.png"))
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn('href="images/page-0002.png" media-type="image/png"', opf)


if __name__ == "__main__":
    unittest.main()
