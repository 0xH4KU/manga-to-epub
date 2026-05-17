import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from pdf_to_epub_lossless import convert_pdf_to_epub
from test_pdf_to_cbz_lossless import _two_page_pdf_with_late_cover


class PdfToEpubLosslessTests(unittest.TestCase):
    def test_epub_uses_pdf_page_order_and_marks_first_image_as_cover(self):
        cover = b"\xff\xd8COVER\xff\xd9"
        page2 = b"\xff\xd8PAGE2\xff\xd9"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover(cover, page2))

            counts = convert_pdf_to_epub(pdf_path, epub_path, title="Comic")

            self.assertEqual({"jpg": 2, "png": 0, "total": 2}, counts)
            with ZipFile(epub_path) as archive:
                names = archive.namelist()
                self.assertEqual("mimetype", names[0])
                self.assertEqual(ZIP_STORED, archive.getinfo("mimetype").compress_type)
                self.assertEqual(b"application/epub+zip", archive.read("mimetype"))
                self.assertEqual(cover, archive.read("EPUB/images/page-0001.jpg"))
                self.assertEqual(page2, archive.read("EPUB/images/page-0002.jpg"))
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn('properties="cover-image"', opf)
                self.assertIn('href="images/page-0001.jpg"', opf)

    def test_epub_contains_page_xhtml_for_each_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())

            convert_pdf_to_epub(pdf_path, epub_path, title="Comic")

            with ZipFile(epub_path) as archive:
                page1 = archive.read("EPUB/xhtml/page-0001.xhtml").decode("utf-8")
                page2 = archive.read("EPUB/xhtml/page-0002.xhtml").decode("utf-8")
                nav = archive.read("EPUB/nav.xhtml").decode("utf-8")
                self.assertIn("../images/page-0001.jpg", page1)
                self.assertIn("../images/page-0002.jpg", page2)
                self.assertIn("Page 1", nav)
                self.assertIn("Page 2", nav)
                self.assertIsNone(archive.testzip())

    def test_apple_books_mode_forces_centered_single_page_spreads(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())

            convert_pdf_to_epub(pdf_path, epub_path, title="Comic", apple_books=True)

            with ZipFile(epub_path) as archive:
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn('<meta property="rendition:spread">none</meta>', opf)
                self.assertIn('<itemref idref="page-0001" properties="rendition:page-spread-center"/>', opf)
                self.assertIn('<itemref idref="page-0002" properties="rendition:page-spread-center"/>', opf)

    def test_blank_pages_after_cover_are_inserted_without_touching_source_images(self):
        cover = b"\xff\xd8COVER\xff\xd9"
        page2 = b"\xff\xd8PAGE2\xff\xd9"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover(cover, page2))

            counts = convert_pdf_to_epub(pdf_path, epub_path, title="Comic", blank_pages_after_cover=2)

            self.assertEqual({"jpg": 2, "png": 0, "blank": 2, "total": 4}, counts)
            with ZipFile(epub_path) as archive:
                names = archive.namelist()
                self.assertIn("EPUB/xhtml/page-0001.xhtml", names)
                self.assertIn("EPUB/xhtml/blank-after-cover-0001.xhtml", names)
                self.assertIn("EPUB/xhtml/blank-after-cover-0002.xhtml", names)
                self.assertIn("EPUB/xhtml/page-0002.xhtml", names)
                self.assertEqual(cover, archive.read("EPUB/images/page-0001.jpg"))
                self.assertEqual(page2, archive.read("EPUB/images/page-0002.jpg"))
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn('<meta property="rendition:spread">auto</meta>', opf)
                self.assertLess(opf.index('idref="page-0001"'), opf.index('idref="blank-after-cover-0001"'))
                self.assertLess(opf.index('idref="blank-after-cover-0002"'), opf.index('idref="page-0002"'))
                self.assertIn('<item id="blank-after-cover-0001"', opf)
                self.assertIn('<item id="blank-after-cover-0002"', opf)

    def test_blank_page_before_cover_is_inserted_before_first_source_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())

            counts = convert_pdf_to_epub(pdf_path, epub_path, title="Comic", blank_pages_before_cover=1)

            self.assertEqual({"jpg": 2, "png": 0, "blank": 1, "total": 3}, counts)
            with ZipFile(epub_path) as archive:
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn('<item id="blank-before-cover-0001"', opf)
                self.assertLess(opf.index('idref="blank-before-cover-0001"'), opf.index('idref="page-0001"'))
                self.assertLess(opf.index('idref="page-0001"'), opf.index('idref="page-0002"'))

    def test_first_two_pages_can_be_explicitly_marked_as_a_spread_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())

            convert_pdf_to_epub(pdf_path, epub_path, title="Comic", pair_first_two_pages=True)

            with ZipFile(epub_path) as archive:
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn('<meta property="rendition:spread">auto</meta>', opf)
                self.assertIn('<itemref idref="page-0001" properties="rendition:page-spread-right"/>', opf)
                self.assertIn('<itemref idref="page-0002" properties="rendition:page-spread-left"/>', opf)

    def test_epub_writes_author_language_and_selected_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())

            convert_pdf_to_epub(
                pdf_path,
                epub_path,
                title="Comic & More",
                author="A&B Studio",
                language="ja",
                cover_item_id="page-0002",
            )

            with ZipFile(epub_path) as archive:
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn("<dc:title>Comic &amp; More</dc:title>", opf)
                self.assertIn("<dc:creator>A&amp;B Studio</dc:creator>", opf)
                self.assertIn("<dc:language>ja</dc:language>", opf)
                self.assertNotIn('id="img-0001" href="images/page-0001.jpg" media-type="image/jpeg" properties="cover-image"', opf)
                self.assertIn('id="img-0002" href="images/page-0002.jpg" media-type="image/jpeg" properties="cover-image"', opf)


if __name__ == "__main__":
    unittest.main()
