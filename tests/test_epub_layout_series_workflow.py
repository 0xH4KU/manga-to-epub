import tempfile
import unittest
from pathlib import Path

from manga_pdf_to_epub.gui.layout_series_workflow import series_export_preflight
from manga_pdf_to_epub.models.series import SeriesProject
from tests.helpers import two_page_pdf_with_late_cover


class EpubLayoutSeriesWorkflowTests(unittest.TestCase):
    def test_series_export_preflight_reports_existing_ready_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "Series Vol.01.pdf"
            output_dir = Path(tmp) / "out"
            output_dir.mkdir()
            pdf_path.write_bytes(two_page_pdf_with_late_cover())
            existing = output_dir / "Series Vol.01.epub"
            existing.write_bytes(b"existing")
            project = SeriesProject.from_pdfs([pdf_path], title="Series")
            project.volumes[0].status = "Ready"

            preflight = series_export_preflight(project, output_dir)

            self.assertEqual({"ready": 1, "failed": 0, "warnings": 0}, preflight.summary)
            self.assertEqual(
                ["Vol.01: output exists and will not be overwritten: Series Vol.01.epub"],
                preflight.existing_output_lines,
            )


if __name__ == "__main__":
    unittest.main()
