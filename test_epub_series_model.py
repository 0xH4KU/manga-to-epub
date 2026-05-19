import tempfile
import unittest
from pathlib import Path

from epub_series_model import SeriesProject
from test_pdf_to_cbz_lossless import _two_page_pdf_with_late_cover


class EpubSeriesModelTests(unittest.TestCase):
    def test_import_pdfs_sorts_volumes_and_generates_titles_from_series_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            vol10 = Path(tmp) / "晚安,布布 淺野一二O Vol.10.pdf"
            vol02 = Path(tmp) / "晚安,布布 淺野一二O Vol.02.pdf"
            vol01 = Path(tmp) / "晚安,布布 淺野一二O Vol.01.pdf"
            for path in (vol10, vol02, vol01):
                path.write_bytes(_two_page_pdf_with_late_cover())

            project = SeriesProject.from_pdfs(
                [vol10, vol02, vol01],
                title="晚安,布布",
                author="淺野一二O",
                language="ja",
            )

            self.assertEqual([vol01, vol02, vol10], [volume.pdf_path for volume in project.volumes])
            self.assertEqual([1, 2, 10], [volume.volume_number for volume in project.volumes])
            self.assertEqual(
                ["晚安,布布 Vol.01", "晚安,布布 Vol.02", "晚安,布布 Vol.10"],
                [project.generated_title(volume) for volume in project.volumes],
            )
            self.assertEqual(["Unreviewed", "Unreviewed", "Unreviewed"], [volume.status for volume in project.volumes])
            self.assertEqual("淺野一二O", project.author)
            self.assertEqual("ja", project.language)

    def test_import_pdfs_uses_sorted_position_when_volume_token_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "Series c.pdf"
            second = Path(tmp) / "Series d.pdf"
            for path in (second, first):
                path.write_bytes(_two_page_pdf_with_late_cover())

            project = SeriesProject.from_pdfs([second, first], title="Series")

            self.assertEqual([first, second], [volume.pdf_path for volume in project.volumes])
            self.assertEqual([1, 2], [volume.volume_number for volume in project.volumes])
            self.assertEqual(["Series Vol.01", "Series Vol.02"], [project.generated_title(v) for v in project.volumes])

    def test_volume_model_uses_series_metadata_not_copied_first_volume_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "晚安,布布 淺野一二O Vol.01.pdf"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            project = SeriesProject.from_pdfs([pdf_path], title="晚安,布布", author="淺野一二O", language="ja")

            model = project.model_for_volume(project.volumes[0])

            self.assertEqual("晚安,布布 Vol.01", model.title)
            self.assertEqual("淺野一二O", model.author)
            self.assertEqual("ja", model.language)


if __name__ == "__main__":
    unittest.main()
