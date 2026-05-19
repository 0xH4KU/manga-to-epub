import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

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

    def test_import_pdfs_infers_bracketed_series_title_and_author(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "[晚安,布布][淺野一二O] Vol.09.pdf"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())

            project = SeriesProject.from_pdfs([pdf_path])

            self.assertEqual("晚安,布布", project.title)
            self.assertEqual("淺野一二O", project.author)
            self.assertEqual("晚安,布布 Vol.09", project.generated_title(project.volumes[0]))

    def test_import_pdfs_infers_plain_series_title_and_author_when_title_has_comma(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "晚安,布布 淺野一二O Vol.01.pdf"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())

            project = SeriesProject.from_pdfs([pdf_path])

            self.assertEqual("晚安,布布", project.title)
            self.assertEqual("淺野一二O", project.author)
            self.assertEqual("晚安,布布 Vol.01", project.generated_title(project.volumes[0]))

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

    def test_export_ready_exports_only_ready_volumes_with_series_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready_pdf = Path(tmp) / "晚安,布布 淺野一二O Vol.01.pdf"
            edited_pdf = Path(tmp) / "晚安,布布 淺野一二O Vol.02.pdf"
            unreviewed_pdf = Path(tmp) / "晚安,布布 淺野一二O Vol.03.pdf"
            output_dir = Path(tmp) / "out"
            for path in (ready_pdf, edited_pdf, unreviewed_pdf):
                path.write_bytes(_two_page_pdf_with_late_cover())
            project = SeriesProject.from_pdfs(
                [unreviewed_pdf, ready_pdf, edited_pdf],
                title="晚安,布布",
                author="淺野一二O",
                language="ja",
            )
            project.volumes[0].status = "Ready"
            project.volumes[1].status = "Edited"

            summary = project.export_ready(output_dir)

            self.assertEqual({"exported": 1, "failed": 0, "skipped": 2}, summary)
            self.assertEqual(["Exported", "Edited", "Unreviewed"], [volume.status for volume in project.volumes])
            exported_path = output_dir / "晚安,布布 Vol.01.epub"
            self.assertTrue(exported_path.exists())
            self.assertFalse((output_dir / "晚安,布布 Vol.02.epub").exists())
            with ZipFile(exported_path) as archive:
                opf = archive.read("EPUB/content.opf").decode("utf-8")
                self.assertIn("<dc:title>晚安,布布 Vol.01</dc:title>", opf)
                self.assertIn("<dc:creator>淺野一二O</dc:creator>", opf)
                self.assertIn("<dc:language>ja</dc:language>", opf)

    def test_mark_volume_ready_updates_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "Series Vol.01.pdf"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            project = SeriesProject.from_pdfs([pdf_path], title="Series")

            project.mark_ready(project.volumes[0])

            self.assertEqual("Ready", project.volumes[0].status)


if __name__ == "__main__":
    unittest.main()
