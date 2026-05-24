import tempfile
import unittest
import json
from pathlib import Path
from zipfile import ZipFile

from manga_pdf_to_epub.models.layout import LayoutModel
from manga_pdf_to_epub.pdf.image_types import PdfImageError
from tests.helpers import four_page_pdf, one_page_pdf, tiny_png, two_page_pdf_with_late_cover


class EpubLayoutModelTests(unittest.TestCase):
    def test_source_pdf_pages_are_loaded_lazily_in_layout_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())

            model = LayoutModel.from_pdf(pdf_path)

            self.assertIsNone(model.entries[0].page.image_data)
            self.assertIsNotNone(model.entries[0].page.image_data_loader)

    def test_inserts_blank_page_at_arbitrary_position_and_exports_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
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

    def test_deletes_blank_entries_through_general_delete_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)

            model.insert_blank(0)
            model.delete_entry(0)

            self.assertEqual(["Page 1", "Page 2"], [entry.label for entry in model.entries])

    def test_blank_only_delete_api_is_removed(self):
        self.assertFalse(hasattr(LayoutModel, "delete_blank"))

    def test_delete_entry_can_remove_source_pages_and_export_without_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
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
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            other_pdf_path.write_bytes(two_page_pdf_with_late_cover())
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
            payload = json.loads(preset_path.read_text(encoding="utf-8"))
            self.assertEqual(2, payload["version"])

    def test_preset_preserves_deleted_source_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            other_pdf_path = Path(tmp) / "other.pdf"
            preset_path = Path(tmp) / "layout.json"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            other_pdf_path.write_bytes(two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)
            model.delete_entry(1)
            model.insert_blank(1)

            model.save_preset(preset_path)
            applied = LayoutModel.from_pdf(other_pdf_path)
            applied.apply_preset(preset_path)

            self.assertEqual(["Page 1", "Blank 1"], [entry.label for entry in applied.entries])

    def test_version_1_preset_still_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            preset_path = Path(tmp) / "layout-v1.json"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            preset_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "source_page_count": 2,
                        "blank_positions": [0, 2],
                        "deleted_source_pages": [2],
                    }
                ),
                encoding="utf-8",
            )
            model = LayoutModel.from_pdf(pdf_path)

            model.apply_preset(preset_path)

            self.assertEqual(["Blank 1", "Page 1", "Blank 2"], [entry.label for entry in model.entries])

    def test_version_2_preset_round_trip_preserves_layout_metadata_and_inserted_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            other_pdf_path = Path(tmp) / "other.pdf"
            image_path = Path(tmp) / "cover.png"
            preset_path = Path(tmp) / "layout-v2.json"
            pdf_path.write_bytes(four_page_pdf())
            other_pdf_path.write_bytes(four_page_pdf())
            image_path.write_bytes(tiny_png())
            model = LayoutModel.from_pdf(pdf_path)
            model.title = "Preset Title"
            model.author = "Preset Author"
            model.language = "ja"
            model.exclude_cover_from_reading = True
            model.delete_range(1, 1)
            model.insert_blank(1)
            model.insert_image(2, image_path)
            model.set_cover_entry(model.entries[2])

            model.save_preset(preset_path)
            payload = json.loads(preset_path.read_text(encoding="utf-8"))
            applied = LayoutModel.from_pdf(other_pdf_path)
            applied.apply_preset(preset_path)

            self.assertEqual(2, payload["version"])
            self.assertEqual(
                [
                    {"kind": "source", "source_index": 1},
                    {"kind": "blank"},
                    {"kind": "inserted", "path": str(image_path), "entry_id": "inserted-0001"},
                    {"kind": "source", "source_index": 3},
                    {"kind": "source", "source_index": 4},
                ],
                payload["entries"],
            )
            self.assertEqual(
                ["Page 1", "Blank 1", "cover", "Page 3", "Page 4"],
                [entry.label for entry in applied.entries],
            )
            self.assertEqual("Preset Title", applied.title)
            self.assertEqual("Preset Author", applied.author)
            self.assertEqual("ja", applied.language)
            self.assertTrue(applied.exclude_cover_from_reading)
            self.assertEqual("inserted-0001", applied.cover_entry_id)

    def test_legacy_version_2_inserted_cover_without_entry_id_uses_inserted_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            preset_path = Path(tmp) / "layout-v2.json"
            image_path = Path(tmp) / "cover.png"
            pdf_path.write_bytes(four_page_pdf())
            image_path.write_bytes(tiny_png())
            preset_path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "source_page_count": 4,
                        "metadata": {
                            "title": "Comic",
                            "author": "",
                            "language": "zh-Hant",
                            "exclude_cover_from_reading": False,
                        },
                        "cover": {"kind": "inserted", "source_index": None},
                        "entries": [
                            {"kind": "source", "source_index": 1},
                            {"kind": "inserted", "path": str(image_path)},
                            {"kind": "source", "source_index": 2},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            model = LayoutModel.from_pdf(pdf_path)

            model.apply_preset(preset_path)

            self.assertEqual("inserted-0001", model.cover_entry_id)
            self.assertIsNone(model.cover_source_index)

    def test_to_preset_payload_matches_saved_version_2_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            image_path = Path(tmp) / "cover.png"
            preset_path = Path(tmp) / "layout-v2.json"
            pdf_path.write_bytes(four_page_pdf())
            image_path.write_bytes(tiny_png())
            model = LayoutModel.from_pdf(pdf_path)
            model.title = "Preset Title"
            model.author = "Preset Author"
            model.language = "ja"
            model.insert_blank(1)
            model.insert_image(2, image_path)
            model.set_cover_entry(model.entries[2])

            payload = model.to_preset_payload()
            model.save_preset(preset_path)

            self.assertEqual(json.loads(preset_path.read_text(encoding="utf-8")), payload)

    def test_version_2_preset_missing_inserted_image_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            preset_path = Path(tmp) / "layout-v2.json"
            missing_path = Path(tmp) / "missing.png"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            preset_path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "source_page_count": 2,
                        "metadata": {
                            "title": "Comic",
                            "author": "",
                            "language": "zh-Hant",
                            "exclude_cover_from_reading": False,
                        },
                        "cover": {"kind": "first-image", "source_index": None, "entry_id": None},
                        "entries": [
                            {"kind": "source", "source_index": 1},
                            {"kind": "inserted", "path": str(missing_path)},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            model = LayoutModel.from_pdf(pdf_path)

            with self.assertRaisesRegex(ValueError, "Inserted image not found"):
                model.apply_preset(preset_path)

    def test_delete_range_returns_entries_for_grouped_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)

            deleted = model.delete_range(1, 2)

            self.assertEqual(["Page 1", "Page 4"], [entry.label for entry in model.entries])
            self.assertEqual([(1, "Page 2"), (2, "Page 3")], [(index, entry.label) for index, entry in deleted])

    def test_quick_delete_helpers_reject_invalid_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
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
            pdf_path.write_bytes(four_page_pdf())
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
            pdf_path.write_bytes(four_page_pdf())
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
            pdf_path.write_bytes(four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)
            model.set_cover(3)

            model.delete_range(2, 2)

            self.assertEqual(1, model.cover_source_index)

    def test_move_entry_reorders_source_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)

            final_index = model.move_entry(3, 1)

            self.assertEqual(1, final_index)
            self.assertEqual(["Page 1", "Page 4", "Page 2", "Page 3"], [entry.label for entry in model.entries])

    def test_move_entry_down_uses_final_visible_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)

            final_index = model.move_entry(1, 3)

            self.assertEqual(3, final_index)
            self.assertEqual(["Page 1", "Page 3", "Page 4", "Page 2"], [entry.label for entry in model.entries])

    def test_move_entry_allows_blank_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)
            model.insert_blank(1)

            final_index = model.move_entry(1, 2)

            self.assertEqual(2, final_index)
            self.assertEqual(["Page 1", "Page 2", "Blank 1"], [entry.label for entry in model.entries])

    def test_move_cover_entry_keeps_cover_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(four_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)
            model.set_cover(3)

            model.move_entry(2, 0)

            self.assertEqual(3, model.cover_source_index)
            self.assertEqual("page-0001", model.normalized_cover_item_id())

    def test_move_entry_rejects_invalid_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)

            with self.assertRaises(IndexError):
                model.move_entry(-1, 0)
            with self.assertRaises(IndexError):
                model.move_entry(0, 2)

    def test_export_selected_images_skips_blanks_and_uses_spine_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            output_dir = Path(tmp) / "images"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)
            model.insert_blank(1)

            exported, skipped = model.export_selected_images([0, 1, 2], output_dir)

            self.assertEqual(["0001.jpg", "0003.jpg"], [path.name for path in exported])
            self.assertEqual(1, skipped)
            self.assertEqual(b"\xff\xd8COVER\xff\xd9", (output_dir / "0001.jpg").read_bytes())
            self.assertEqual(b"\xff\xd8PAGE2\xff\xd9", (output_dir / "0003.jpg").read_bytes())

    def test_insert_external_png_exports_as_epub_page_and_selected_image(self):
        png = tiny_png()
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            image_path = Path(tmp) / "extra.png"
            epub_path = Path(tmp) / "comic.epub"
            output_dir = Path(tmp) / "selected"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
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

    def test_inserted_image_payload_is_loaded_lazily(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            image_path = Path(tmp) / "extra.png"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            image_path.write_bytes(tiny_png())
            model = LayoutModel.from_pdf(pdf_path)

            model.insert_image(1, image_path)

            self.assertIsNone(model.entries[1].page.image_data)
            self.assertIsNotNone(model.entries[1].page.image_data_loader)

    def test_inserted_image_can_be_set_as_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            image_path = Path(tmp) / "cover.png"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            image_path.write_bytes(tiny_png())
            model = LayoutModel.from_pdf(pdf_path)

            model.insert_image(1, image_path)
            model.set_cover_entry(model.entries[1])
            model.export_epub(epub_path, overwrite=True)

            with ZipFile(epub_path) as archive:
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn(
                    'id="img-0002" href="images/page-0002.png" media-type="image/png" properties="cover-image"',
                    opf,
                )

    def test_inserted_image_ids_do_not_reuse_after_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            first_image = Path(tmp) / "first.png"
            second_image = Path(tmp) / "second.png"
            third_image = Path(tmp) / "third.png"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            first_image.write_bytes(tiny_png())
            second_image.write_bytes(tiny_png())
            third_image.write_bytes(tiny_png())
            model = LayoutModel.from_pdf(pdf_path)
            model.insert_image(1, first_image)
            model.insert_image(2, second_image)

            model.delete_entry(1)
            model.insert_image(2, third_image)

            inserted_ids = [
                entry.page.item_id
                for entry in model.entries
                if entry.source_index is None and not entry.is_blank
            ]
            self.assertEqual(["inserted-0002", "inserted-0003"], inserted_ids)

    def test_v2_preset_preserves_inserted_cover_identity_after_deleted_inserted_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            other_pdf_path = Path(tmp) / "other.pdf"
            first_image = Path(tmp) / "first.png"
            second_image = Path(tmp) / "second.png"
            third_image = Path(tmp) / "third.png"
            for path in (pdf_path, other_pdf_path):
                path.write_bytes(four_page_pdf())
            for path in (first_image, second_image, third_image):
                path.write_bytes(tiny_png())
            model = LayoutModel.from_pdf(pdf_path)
            model.insert_image(1, first_image)
            model.insert_image(2, second_image)
            model.insert_image(3, third_image)
            model.set_cover_entry(model.entries[3])
            model.delete_entry(1)

            payload = model.to_preset_payload()
            applied = LayoutModel.from_pdf(other_pdf_path)
            applied.apply_preset_payload(payload)

            inserted_entries = [
                (entry.label, entry.page.item_id)
                for entry in applied.entries
                if entry.source_index is None and not entry.is_blank
            ]
            self.assertEqual([("second", "inserted-0002"), ("third", "inserted-0003")], inserted_entries)
            self.assertEqual("inserted-0003", applied.cover_entry_id)
            cover_label = next(
                entry.label
                for entry, page in zip(applied.entries, applied.normalized_pages())
                if page.item_id == applied.normalized_cover_item_id()
            )
            self.assertEqual("third", cover_label)

    def test_inserted_cover_can_be_excluded_from_reading_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            image_path = Path(tmp) / "cover.png"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            image_path.write_bytes(tiny_png())
            model = LayoutModel.from_pdf(pdf_path)
            model.insert_image(1, image_path)
            model.set_cover_entry(model.entries[1])
            model.exclude_cover_from_reading = True

            counts = model.export_epub(epub_path, overwrite=True)

            self.assertEqual(2, counts["total"])
            with ZipFile(epub_path) as archive:
                names = archive.namelist()
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn("EPUB/images/page-0002.png", names)
                self.assertNotIn("EPUB/xhtml/page-0002.xhtml", names)
                self.assertIn('properties="cover-image"', opf)
                self.assertNotIn('idref="page-0002"', opf)

    def test_deleting_inserted_cover_falls_back_to_first_source_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            image_path = Path(tmp) / "cover.png"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            image_path.write_bytes(tiny_png())
            model = LayoutModel.from_pdf(pdf_path)
            model.insert_image(0, image_path)
            model.set_cover_entry(model.entries[0])

            model.delete_entry(0)

            self.assertEqual(1, model.cover_source_index)
            self.assertEqual("page-0001", model.normalized_cover_item_id())

    def test_model_can_exclude_cover_from_reading_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(pdf_path)
            model.exclude_cover_from_reading = True

            counts = model.export_epub(epub_path, overwrite=True, title="Comic")

            self.assertEqual({"jpg": 2, "png": 0, "total": 1}, counts)
            with ZipFile(epub_path) as archive:
                names = archive.namelist()
                self.assertNotIn("EPUB/xhtml/page-0001.xhtml", names)
                self.assertIn("EPUB/xhtml/page-0002.xhtml", names)
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn('properties="cover-image"', opf)
                self.assertNotIn('idref="page-0001"', opf)
                self.assertIn('idref="page-0002"', opf)

    def test_model_rejects_cover_only_export_without_reading_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "comic.pdf"
            epub_path = Path(tmp) / "comic.epub"
            pdf_path.write_bytes(one_page_pdf())
            model = LayoutModel.from_pdf(pdf_path)
            model.exclude_cover_from_reading = True

            with self.assertRaisesRegex(PdfImageError, "Cover-only export would leave no reading pages"):
                model.export_epub(epub_path, overwrite=True, title="Comic")

            self.assertFalse(epub_path.exists())


if __name__ == "__main__":
    unittest.main()
