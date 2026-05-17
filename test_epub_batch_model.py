import tempfile
import unittest
from pathlib import Path

from epub_batch_model import BatchProject
from epub_layout_model import LayoutModel
from test_epub_layout_model import _four_page_pdf
from test_pdf_to_cbz_lossless import _two_page_pdf_with_late_cover


class EpubBatchModelTests(unittest.TestCase):
    def test_template_validation_marks_matching_pdf_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample_pdf = Path(tmp) / "sample.pdf"
            other_pdf = Path(tmp) / "other.pdf"
            sample_pdf.write_bytes(_two_page_pdf_with_late_cover())
            other_pdf.write_bytes(_two_page_pdf_with_late_cover())
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
            sample_pdf.write_bytes(_two_page_pdf_with_late_cover())
            mismatch_pdf.write_bytes(_four_page_pdf())
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
            sample_pdf.write_bytes(_two_page_pdf_with_late_cover())
            good_pdf.write_bytes(_two_page_pdf_with_late_cover())
            bad_pdf.write_text("not a pdf", encoding="utf-8")
            project = BatchProject.from_template(LayoutModel.from_pdf(sample_pdf))
            good = project.add_pdf(good_pdf)
            bad = project.add_pdf(bad_pdf)

            summary = project.export_all(output_dir)

            self.assertEqual({"exported": 1, "failed": 1, "skipped": 0}, summary)
            self.assertEqual("Exported", good.status)
            self.assertEqual("Failed", bad.status)
            self.assertTrue((output_dir / "good.epub").exists())


if __name__ == "__main__":
    unittest.main()
