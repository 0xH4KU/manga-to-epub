import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile
from contextlib import redirect_stderr
from unittest.mock import patch

from manga_pdf_to_epub.pdf_image_types import PdfImageError
from manga_pdf_to_epub.pdf_to_epub_lossless import (
    EpubPage,
    _media_type_for_ext,
    _validate_epub_structure,
    convert_pdf_to_epub,
    main,
    write_epub_from_pages,
)
from tests.helpers import four_page_pdf, tiny_png
from tests.helpers import two_page_pdf_with_late_cover


class PdfToEpubLosslessTests(unittest.TestCase):
    def test_epub_uses_pdf_page_order_and_marks_first_image_as_cover(self):
        cover = b"\xff\xd8COVER\xff\xd9"
        page2 = b"\xff\xd8PAGE2\xff\xd9"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover(cover, page2))

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

    def test_direct_conversion_builds_pages_with_lazy_pdf_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

            with patch("manga_pdf_to_epub.pdf_to_epub_lossless.write_epub_from_pages") as write_epub:
                write_epub.return_value = {"jpg": 2, "png": 0, "total": 2}

                convert_pdf_to_epub(pdf_path, epub_path, title="Comic")

            pages = write_epub.call_args.args[0]
            self.assertIsNone(pages[0].image_data)
            self.assertIsNotNone(pages[0].image_data_loader)

    def test_epub_contains_page_xhtml_for_each_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

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
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

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
            pdf_path.write_bytes(two_page_pdf_with_late_cover(cover, page2))

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
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

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
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

            convert_pdf_to_epub(pdf_path, epub_path, title="Comic", pair_first_two_pages=True)

            with ZipFile(epub_path) as archive:
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn('<meta property="rendition:spread">auto</meta>', opf)
                self.assertIn('<itemref idref="page-0001" properties="rendition:page-spread-right"/>', opf)
                self.assertIn('<itemref idref="page-0002" properties="rendition:page-spread-left"/>', opf)

    def test_cli_rejects_conflicting_spread_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            stderr = io.StringIO()

            with patch("sys.argv", ["pdf_to_epub_lossless.py", str(pdf_path), "--apple-books", "--pair-first-two-pages"]):
                with redirect_stderr(stderr):
                    with self.assertRaisesRegex(SystemExit, "2"):
                        main()

        written = stderr.getvalue()
        self.assertIn("--apple-books", written)
        self.assertIn("--pair-first-two-pages", written)

    def test_cli_metadata_cover_page_and_cover_only_write_opf(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            output_dir = Path(tmp) / "out"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

            with patch(
                "sys.argv",
                [
                    "pdf_to_epub_lossless.py",
                    str(pdf_path),
                    "--output-dir",
                    str(output_dir),
                    "--title",
                    "Comic & More",
                    "--author",
                    "A&B Studio",
                    "--language",
                    "ja",
                    "--cover-page",
                    "2",
                    "--cover-only",
                    "--overwrite",
                ],
            ):
                self.assertEqual(0, main())

            epub_path = output_dir / "comic.epub"
            with ZipFile(epub_path) as archive:
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn("<dc:title>Comic &amp; More</dc:title>", opf)
                self.assertIn("<dc:creator>A&amp;B Studio</dc:creator>", opf)
                self.assertIn("<dc:language>ja</dc:language>", opf)
                self.assertIn('id="img-0002" href="images/page-0002.jpg" media-type="image/jpeg" properties="cover-image"', opf)
                self.assertNotIn('idref="page-0002"', opf)

    def test_cli_invalid_cover_page_fails_before_writing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            output_dir = Path(tmp) / "out"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

            with patch(
                "sys.argv",
                [
                    "pdf_to_epub_lossless.py",
                    str(pdf_path),
                    "--output-dir",
                    str(output_dir),
                    "--cover-page",
                    "9",
                ],
            ):
                with self.assertRaisesRegex(PdfImageError, "Invalid cover page: 9"):
                    main()

            self.assertFalse((output_dir / "comic.epub").exists())

    def test_cli_preset_applies_blank_and_deleted_page_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            output_dir = Path(tmp) / "out"
            preset_path = Path(tmp) / "layout.json"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            preset_path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "source_page_count": 2,
                        "metadata": {"title": "Preset Title", "author": "", "language": "zh-Hant"},
                        "cover": {"kind": "first-image", "source_index": None, "entry_id": None},
                        "entries": [
                            {"kind": "source", "source_index": 1},
                            {"kind": "blank"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "sys.argv",
                [
                    "pdf_to_epub_lossless.py",
                    str(pdf_path),
                    "--output-dir",
                    str(output_dir),
                    "--preset",
                    str(preset_path),
                    "--overwrite",
                ],
            ):
                self.assertEqual(0, main())

            with ZipFile(output_dir / "comic.epub") as archive:
                names = archive.namelist()
                self.assertIn("EPUB/xhtml/blank-0001.xhtml", names)
                self.assertNotIn("EPUB/images/page-0002.jpg", names)

    def test_cli_delete_range_normalizes_exported_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            output_dir = Path(tmp) / "out"
            pdf_path.write_bytes(four_page_pdf())

            with patch(
                "sys.argv",
                [
                    "pdf_to_epub_lossless.py",
                    str(pdf_path),
                    "--output-dir",
                    str(output_dir),
                    "--delete-range",
                    "1-3",
                    "--overwrite",
                ],
            ):
                self.assertEqual(0, main())

            with ZipFile(output_dir / "comic.epub") as archive:
                self.assertIn("EPUB/images/page-0001.jpg", archive.namelist())
                self.assertNotIn("EPUB/images/page-0004.jpg", archive.namelist())
                nav = archive.read("EPUB/nav.xhtml").decode("utf-8")
                self.assertIn("Page 4", nav)

    def test_cli_insert_image_after_adds_external_png_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            image_path = Path(tmp) / "extra.png"
            output_dir = Path(tmp) / "out"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            image_path.write_bytes(tiny_png())

            with patch(
                "sys.argv",
                [
                    "pdf_to_epub_lossless.py",
                    str(pdf_path),
                    "--output-dir",
                    str(output_dir),
                    "--insert-image-after",
                    f"1={image_path}",
                    "--overwrite",
                ],
            ):
                self.assertEqual(0, main())

            with ZipFile(output_dir / "comic.epub") as archive:
                self.assertEqual(tiny_png(), archive.read("EPUB/images/page-0002.png"))

    def test_cli_series_title_and_volume_number_generate_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            output_dir = Path(tmp) / "out"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

            with patch(
                "sys.argv",
                [
                    "pdf_to_epub_lossless.py",
                    str(pdf_path),
                    "--output-dir",
                    str(output_dir),
                    "--series-title",
                    "Series",
                    "--volume-number",
                    "7",
                    "--overwrite",
                ],
            ):
                self.assertEqual(0, main())

            with ZipFile(output_dir / "comic.epub") as archive:
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn("<dc:title>Series Vol.07</dc:title>", opf)

    def test_epub_writes_author_language_and_selected_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

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

    def test_cover_image_can_be_excluded_from_reading_pages(self):
        cover = b"\xff\xd8COVER\xff\xd9"
        page2 = b"\xff\xd8PAGE2\xff\xd9"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover(cover, page2))

            counts = convert_pdf_to_epub(
                pdf_path,
                epub_path,
                title="Comic",
                cover_item_id="page-0001",
                exclude_cover_from_reading=True,
            )

            self.assertEqual({"jpg": 2, "png": 0, "total": 1}, counts)
            with ZipFile(epub_path) as archive:
                names = archive.namelist()
                self.assertEqual(cover, archive.read("EPUB/images/page-0001.jpg"))
                self.assertEqual(page2, archive.read("EPUB/images/page-0002.jpg"))
                self.assertNotIn("EPUB/xhtml/page-0001.xhtml", names)
                self.assertIn("EPUB/xhtml/page-0002.xhtml", names)
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                nav = archive.read("EPUB/nav.xhtml").decode("utf-8")
                self.assertIn('id="img-0001" href="images/page-0001.jpg" media-type="image/jpeg" properties="cover-image"', opf)
                self.assertIn('id="page-0002" href="xhtml/page-0002.xhtml"', opf)
                self.assertNotIn('id="page-0001" href="xhtml/page-0001.xhtml"', opf)
                self.assertNotIn('idref="page-0001"', opf)
                self.assertIn('idref="page-0002"', opf)
                self.assertNotIn("Page 1", nav)
                self.assertIn("Page 2", nav)

    def test_invalid_cover_item_id_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "comic.epub"
            page = EpubPage(
                index=1,
                width=2,
                height=1,
                image_href="images/page-0001.jpg",
                image_media_type="image/jpeg",
                image_data=b"\xff\xd8PAGE1\xff\xd9",
                xhtml_href="xhtml/page-0001.xhtml",
                item_id="page-0001",
                label="Page 1",
            )

            with self.assertRaisesRegex(PdfImageError, "Invalid cover item ID: missing-page"):
                write_epub_from_pages(
                    [page],
                    epub_path,
                    source_path=Path(tmp) / "comic.pdf",
                    title="Comic",
                    cover_item_id="missing-page",
                )

            self.assertFalse(epub_path.exists())

    def test_cover_only_cannot_remove_all_reading_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "comic.epub"
            page = EpubPage(
                index=1,
                width=2,
                height=1,
                image_href="images/page-0001.jpg",
                image_media_type="image/jpeg",
                image_data=b"\xff\xd8PAGE1\xff\xd9",
                xhtml_href="xhtml/page-0001.xhtml",
                item_id="page-0001",
                label="Page 1",
            )

            with self.assertRaisesRegex(PdfImageError, "Cover-only export would leave no reading pages"):
                write_epub_from_pages(
                    [page],
                    epub_path,
                    source_path=Path(tmp) / "comic.pdf",
                    title="Comic",
                    cover_item_id="page-0001",
                    exclude_cover_from_reading=True,
                )

            self.assertFalse(epub_path.exists())

    def test_unsupported_epub_image_extension_fails_clearly(self):
        with self.assertRaisesRegex(PdfImageError, "Unsupported image extension for EPUB: gif"):
            _media_type_for_ext("gif")

    def test_valid_generated_epub_passes_structure_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            convert_pdf_to_epub(pdf_path, epub_path, title="Comic")

            _validate_epub_structure(epub_path)

    def test_structure_validation_rejects_missing_spine_manifest_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "broken.epub"
            with ZipFile(epub_path, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip")
                archive.writestr("META-INF/container.xml", b"<container/>")
                archive.writestr("EPUB/nav.xhtml", b"<html/>")
                archive.writestr(
                    "EPUB/content.opf",
                    """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf">
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  </manifest>
  <spine><itemref idref="missing-page"/></spine>
</package>
""",
                )

            with self.assertRaisesRegex(PdfImageError, "Spine itemref missing-page has no manifest item"):
                _validate_epub_structure(epub_path)

    def test_structure_validation_rejects_missing_manifest_href(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "broken.epub"
            with ZipFile(epub_path, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip")
                archive.writestr("META-INF/container.xml", b"<container/>")
                archive.writestr(
                    "EPUB/content.opf",
                    """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf">
  <manifest>
    <item id="page-0001" href="xhtml/page-0001.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="page-0001"/></spine>
</package>
""",
                )

            with self.assertRaisesRegex(PdfImageError, "Manifest href missing from EPUB: EPUB/xhtml/page-0001.xhtml"):
                _validate_epub_structure(epub_path)

    def test_structure_validation_rejects_duplicate_zip_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "broken.epub"
            with ZipFile(epub_path, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip")
                archive.writestr("mimetype", b"application/epub+zip")

            with self.assertRaisesRegex(PdfImageError, "Duplicate EPUB zip entry: mimetype"):
                _validate_epub_structure(epub_path)

    def test_structure_validation_rejects_malformed_xhtml(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "broken.epub"
            with ZipFile(epub_path, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip")
                archive.writestr("META-INF/container.xml", b"<container/>")
                archive.writestr("EPUB/xhtml/page-0001.xhtml", b"<html><body></html>")
                archive.writestr(
                    "EPUB/content.opf",
                    """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf">
  <manifest>
    <item id="page-0001" href="xhtml/page-0001.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="page-0001"/></spine>
</package>
""",
                )

            with self.assertRaisesRegex(PdfImageError, "Malformed XHTML file: EPUB/xhtml/page-0001.xhtml"):
                _validate_epub_structure(epub_path)

    def test_structure_validation_rejects_missing_nav_manifest_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "broken.epub"
            with ZipFile(epub_path, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip")
                archive.writestr("META-INF/container.xml", b"<container/>")
                archive.writestr(
                    "EPUB/content.opf",
                    """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf">
  <manifest>
    <item id="page-0001" href="xhtml/page-0001.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="page-0001"/></spine>
</package>
""",
                )
                archive.writestr("EPUB/xhtml/page-0001.xhtml", b"<html/>")

            with self.assertRaisesRegex(PdfImageError, "EPUB nav item missing"):
                _validate_epub_structure(epub_path)

    def test_structure_validation_rejects_wrong_image_media_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "broken.epub"
            with ZipFile(epub_path, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip")
                archive.writestr("META-INF/container.xml", b"<container/>")
                archive.writestr("EPUB/nav.xhtml", b"<html/>")
                archive.writestr("EPUB/images/page-0001.png", b"PNG")
                archive.writestr("EPUB/xhtml/page-0001.xhtml", b"<html/>")
                archive.writestr(
                    "EPUB/content.opf",
                    """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf">
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="img-0001" href="images/page-0001.png" media-type="image/jpeg"/>
    <item id="page-0001" href="xhtml/page-0001.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="page-0001"/></spine>
</package>
""",
                )

            with self.assertRaisesRegex(PdfImageError, "Image media type mismatch for EPUB/images/page-0001.png"):
                _validate_epub_structure(epub_path)

    def test_structure_validation_rejects_missing_reading_page_image_manifest_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "broken.epub"
            with ZipFile(epub_path, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip")
                archive.writestr("META-INF/container.xml", b"<container/>")
                archive.writestr("EPUB/nav.xhtml", b'<html xmlns="http://www.w3.org/1999/xhtml" lang="ja" xml:lang="ja"/>')
                archive.writestr(
                    "EPUB/xhtml/page-0001.xhtml",
                    b"""<html xmlns="http://www.w3.org/1999/xhtml" lang="ja" xml:lang="ja">
  <body>
    <svg xmlns="http://www.w3.org/2000/svg">
      <image href="../images/missing.jpg"/>
    </svg>
  </body>
</html>""",
                )
                archive.writestr(
                    "EPUB/content.opf",
                    """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:language>ja</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="page-0001" href="xhtml/page-0001.xhtml" media-type="application/xhtml+xml" properties="svg"/>
  </manifest>
  <spine><itemref idref="page-0001"/></spine>
</package>
""",
                )

            with self.assertRaisesRegex(PdfImageError, "Reading page image missing from manifest: EPUB/images/missing.jpg"):
                _validate_epub_structure(epub_path)

    def test_structure_validation_rejects_cover_image_counts_other_than_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            no_cover = Path(tmp) / "no-cover.epub"
            two_covers = Path(tmp) / "two-covers.epub"

            def write_epub(path: Path, image_items: str) -> None:
                with ZipFile(path, "w") as archive:
                    archive.writestr("mimetype", b"application/epub+zip")
                    archive.writestr("META-INF/container.xml", b"<container/>")
                    archive.writestr("EPUB/nav.xhtml", b'<html xmlns="http://www.w3.org/1999/xhtml" lang="ja" xml:lang="ja"/>')
                    archive.writestr("EPUB/xhtml/page-0001.xhtml", b'<html xmlns="http://www.w3.org/1999/xhtml" lang="ja" xml:lang="ja"/>')
                    archive.writestr("EPUB/images/page-0001.jpg", b"JPG")
                    archive.writestr("EPUB/images/page-0002.jpg", b"JPG")
                    archive.writestr(
                        "EPUB/content.opf",
                        f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:language>ja</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {image_items}
    <item id="page-0001" href="xhtml/page-0001.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="page-0001"/></spine>
</package>
""",
                    )

            write_epub(no_cover, '<item id="img-0001" href="images/page-0001.jpg" media-type="image/jpeg"/>')
            write_epub(
                two_covers,
                """<item id="img-0001" href="images/page-0001.jpg" media-type="image/jpeg" properties="cover-image"/>
    <item id="img-0002" href="images/page-0002.jpg" media-type="image/jpeg" properties="cover-image"/>""",
            )

            with self.assertRaisesRegex(PdfImageError, "EPUB must have exactly one cover image"):
                _validate_epub_structure(no_cover)
            with self.assertRaisesRegex(PdfImageError, "EPUB must have exactly one cover image"):
                _validate_epub_structure(two_covers)

    def test_structure_validation_rejects_inconsistent_xhtml_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "broken.epub"
            with ZipFile(epub_path, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip")
                archive.writestr("META-INF/container.xml", b"<container/>")
                archive.writestr("EPUB/nav.xhtml", b'<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en"/>')
                archive.writestr("EPUB/xhtml/page-0001.xhtml", b'<html xmlns="http://www.w3.org/1999/xhtml" lang="ja" xml:lang="ja"/>')
                archive.writestr("EPUB/images/page-0001.jpg", b"JPG")
                archive.writestr(
                    "EPUB/content.opf",
                    """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:language>ja</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="img-0001" href="images/page-0001.jpg" media-type="image/jpeg" properties="cover-image"/>
    <item id="page-0001" href="xhtml/page-0001.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="page-0001"/></spine>
</package>
""",
                )

            with self.assertRaisesRegex(PdfImageError, "XHTML language mismatch for EPUB/nav.xhtml"):
                _validate_epub_structure(epub_path)

    def test_language_propagates_to_nav_and_page_xhtml(self):
        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "comic.epub"
            page = EpubPage(
                index=1,
                width=2,
                height=1,
                image_href="images/page-0001.jpg",
                image_media_type="image/jpeg",
                image_data=b"\xff\xd8PAGE1\xff\xd9",
                xhtml_href="xhtml/page-0001.xhtml",
                item_id="page-0001",
                label="Page 1",
            )

            write_epub_from_pages([page], epub_path, source_path=Path(tmp) / "comic.pdf", title="Comic", language="ja")

            with ZipFile(epub_path) as archive:
                nav = archive.read("EPUB/nav.xhtml").decode("utf-8")
                page_xhtml = archive.read("EPUB/xhtml/page-0001.xhtml").decode("utf-8")
                self.assertIn('lang="ja" xml:lang="ja"', nav)
                self.assertIn('lang="ja" xml:lang="ja"', page_xhtml)


if __name__ == "__main__":
    unittest.main()
