import tempfile
import unittest
import json
import warnings
from pathlib import Path

from manga_pdf_to_epub.models.batch import BatchProject
from manga_pdf_to_epub.models.layout import LayoutModel
from tests.helpers import four_page_pdf, tiny_png
from tests.helpers import two_page_pdf_with_late_cover


class EpubBatchModelTests(unittest.TestCase):
    def setUp(self):
        warnings.filterwarnings("ignore", message="BatchProject is deprecated.*", category=DeprecationWarning)

    def test_template_validation_marks_matching_pdf_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample_pdf = Path(tmp) / "sample.pdf"
            other_pdf = Path(tmp) / "other.pdf"
            sample_pdf.write_bytes(two_page_pdf_with_late_cover())
            other_pdf.write_bytes(two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(sample_pdf)
            model.insert_blank(1)
            project = BatchProject.from_template(model)

            item = project.add_pdf(other_pdf)
            project.validate_all(Path(tmp) / "out")

            self.assertEqual("Ready", item.status)
            self.assertEqual([], item.warnings)
            self.assertEqual("other", item.title)

    def test_template_validation_warns_when_page_count_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample_pdf = Path(tmp) / "sample.pdf"
            mismatch_pdf = Path(tmp) / "mismatch.pdf"
            sample_pdf.write_bytes(two_page_pdf_with_late_cover())
            mismatch_pdf.write_bytes(four_page_pdf())
            model = LayoutModel.from_pdf(sample_pdf)
            project = BatchProject.from_template(model)

            item = project.add_pdf(mismatch_pdf)
            project.validate_all(Path(tmp) / "out")

            self.assertEqual("Warning", item.status)
            self.assertIn("Page count differs: expected 2, got 4", item.warnings)

    def test_batch_export_continues_after_failed_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample_pdf = Path(tmp) / "sample.pdf"
            good_pdf = Path(tmp) / "good.pdf"
            bad_pdf = Path(tmp) / "bad.pdf"
            output_dir = Path(tmp) / "out"
            sample_pdf.write_bytes(two_page_pdf_with_late_cover())
            good_pdf.write_bytes(two_page_pdf_with_late_cover())
            bad_pdf.write_text("not a pdf", encoding="utf-8")
            project = BatchProject.from_template(LayoutModel.from_pdf(sample_pdf))
            good = project.add_pdf(good_pdf)
            bad = project.add_pdf(bad_pdf)

            summary = project.export_all(output_dir)

            self.assertEqual({"exported": 1, "failed": 1, "skipped": 0}, summary)
            self.assertEqual("Exported", good.status)
            self.assertEqual("Failed", bad.status)
            self.assertTrue((output_dir / "good.epub").exists())

    def test_template_model_for_item_preserves_inserted_cover_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample_pdf = Path(tmp) / "sample.pdf"
            target_pdf = Path(tmp) / "target.pdf"
            image_path = Path(tmp) / "cover.png"
            sample_pdf.write_bytes(four_page_pdf())
            target_pdf.write_bytes(four_page_pdf())
            image_path.write_bytes(tiny_png())
            model = LayoutModel.from_pdf(sample_pdf)
            model.title = "Template Title"
            model.author = "Template Author"
            model.language = "ja"
            model.exclude_cover_from_reading = True
            model.delete_entry(1)
            model.insert_blank(1)
            model.insert_image(2, image_path)
            model.set_cover_entry(model.entries[2])
            project = BatchProject.from_template(model)
            item = project.add_pdf(target_pdf)

            applied = project._model_for_item(item)

            self.assertEqual(["Page 1", "Blank 1", "cover", "Page 3", "Page 4"], [entry.label for entry in applied.entries])
            self.assertEqual("target", applied.title)
            self.assertEqual("Template Author", applied.author)
            self.assertEqual("ja", applied.language)
            self.assertTrue(applied.exclude_cover_from_reading)
            self.assertEqual("inserted-0001", applied.cover_entry_id)

    def test_batch_project_can_be_created_from_v2_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            preset_path = Path(tmp) / "layout.json"
            image_path = Path(tmp) / "cover.png"
            image_path.write_bytes(tiny_png())
            preset_path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "source_page_count": 4,
                        "metadata": {
                            "title": "Template",
                            "author": "Author",
                            "language": "ja",
                            "exclude_cover_from_reading": True,
                        },
                        "cover": {"kind": "inserted", "source_index": None, "entry_id": "inserted-0001"},
                        "entries": [
                            {"kind": "source", "source_index": 1},
                            {"kind": "blank"},
                            {"kind": "inserted", "path": str(image_path)},
                            {"kind": "source", "source_index": 4},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            project = BatchProject.from_preset(preset_path)

            self.assertEqual(4, project.template.source_page_count)
            self.assertEqual([2, 3], project.template.deleted_source_pages)
            self.assertEqual([1], project.template.blank_positions)
            self.assertEqual("Author", project.template.author)
            self.assertEqual("ja", project.template.language)
            self.assertTrue(project.template.exclude_cover_from_reading)
            self.assertEqual("inserted-0001", project.template.cover_entry_id)
            self.assertEqual(4, len(project.template.entries))

    def test_batch_project_warns_that_legacy_workflow_is_deprecated(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample_pdf = Path(tmp) / "sample.pdf"
            sample_pdf.write_bytes(two_page_pdf_with_late_cover())
            model = LayoutModel.from_pdf(sample_pdf)

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                BatchProject.from_template(model)

            self.assertEqual(1, len(caught))
            self.assertTrue(issubclass(caught[0].category, DeprecationWarning))
            self.assertIn("SeriesProject", str(caught[0].message))


if __name__ == "__main__":
    unittest.main()
