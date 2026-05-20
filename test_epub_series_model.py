import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from epub_series_model import SeriesProject
from test_epub_layout_model import _tiny_png
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

            self.assertEqual({"exported": 1, "failed": 0, "skipped": 2, "warnings": 0}, summary)
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

    def test_volumes_for_scope_accepts_commas_ranges_and_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for number in (1, 2, 3, 7):
                path = Path(tmp) / f"Series Vol.{number:02d}.pdf"
                path.write_bytes(_two_page_pdf_with_late_cover())
                paths.append(path)
            project = SeriesProject.from_pdfs(paths, title="Series")

            self.assertEqual([1, 2, 7], [volume.volume_number for volume in project.volumes_for_scope("1,2,7")])
            self.assertEqual([1, 2, 3], [volume.volume_number for volume in project.volumes_for_scope("1-3")])
            self.assertEqual([1, 2, 3, 7], [volume.volume_number for volume in project.volumes_for_scope("all")])

    def test_volumes_for_scope_rejects_invalid_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "Series Vol.01.pdf"
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            project = SeriesProject.from_pdfs([pdf_path], title="Series")

            with self.assertRaisesRegex(ValueError, "Invalid volume scope"):
                project.volumes_for_scope("first")

    def test_project_payload_round_trips_metadata_status_and_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "series-project.json"
            vol01 = Path(tmp) / "Series Vol.01.pdf"
            vol02 = Path(tmp) / "Series Vol.02.pdf"
            inserted_cover = Path(tmp) / "covers" / "cover.png"
            inserted_cover.parent.mkdir()
            for path in (vol01, vol02):
                path.write_bytes(_two_page_pdf_with_late_cover())
            inserted_cover.write_bytes(_tiny_png())
            project = SeriesProject.from_pdfs([vol01, vol02], title="Series", author="Author", language="ja")
            first = project.volumes[0]
            first.status = "Ready"
            first.output_path = Path(tmp) / "out" / "Series Vol.01.epub"
            first.warnings.append("reviewed manually")
            model = project.model_for_volume(first)
            model.insert_blank(1)
            model.insert_image(2, inserted_cover)
            model.set_cover_entry(model.entries[2])
            model.exclude_cover_from_reading = True
            project.volumes[1].status = "Edited"

            payload = project.to_payload(project_path)
            restored = SeriesProject.from_payload(payload, project_path)

            self.assertEqual(1, payload["version"])
            self.assertEqual("Series", restored.title)
            self.assertEqual("Author", restored.author)
            self.assertEqual("ja", restored.language)
            self.assertEqual([vol01, vol02], [volume.pdf_path for volume in restored.volumes])
            self.assertEqual(["Ready", "Edited"], [volume.status for volume in restored.volumes])
            self.assertEqual(Path(tmp) / "out" / "Series Vol.01.epub", restored.volumes[0].output_path)
            self.assertEqual(["reviewed manually"], restored.volumes[0].warnings)
            restored_model = restored.model_for_volume(restored.volumes[0])
            self.assertEqual(["Page 1", "Blank 1", "cover", "Page 2"], [entry.label for entry in restored_model.entries])
            self.assertEqual("inserted-0001", restored_model.cover_entry_id)
            self.assertTrue(restored_model.exclude_cover_from_reading)
            self.assertEqual("Series Vol.01", restored_model.title)
            self.assertEqual("Author", restored_model.author)
            self.assertEqual("ja", restored_model.language)
            self.assertEqual("Series Vol.02", restored.model_for_volume(restored.volumes[1]).title)

    def test_project_payload_uses_relative_paths_when_saved_near_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "projects" / "series-project.json"
            pdf_path = Path(tmp) / "pdfs" / "Series Vol.01.pdf"
            project_path.parent.mkdir()
            pdf_path.parent.mkdir()
            pdf_path.write_bytes(_two_page_pdf_with_late_cover())
            project = SeriesProject.from_pdfs([pdf_path], title="Series")

            payload = project.to_payload(project_path)

            self.assertEqual("../pdfs/Series Vol.01.pdf", payload["volumes"][0]["pdf_path"])
            restored = SeriesProject.from_payload(payload, project_path)
            self.assertEqual(pdf_path, restored.volumes[0].pdf_path)

    def test_validate_all_reports_duplicate_volumes_missing_pdfs_and_filename_collisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing_pdf = Path(tmp) / "Series Vol.01.pdf"
            missing_pdf = Path(tmp) / "Missing Vol.01.pdf"
            output_dir = Path(tmp) / "out"
            existing_pdf.write_bytes(_two_page_pdf_with_late_cover())
            project = SeriesProject.from_pdfs([existing_pdf], title="Series")
            duplicate = type(project.volumes[0])(
                pdf_path=missing_pdf,
                volume_number=1,
                status="Ready",
            )
            project.volumes.append(duplicate)

            summary = project.validate_all(output_dir)

            self.assertEqual({"ready": 1, "failed": 1, "warnings": 2}, summary)
            self.assertEqual(["Output filename collision: Series Vol.01.epub", "Duplicate volume number: 1"], project.volumes[0].warnings)
            self.assertEqual(["Output filename collision: Series Vol.01.epub", "Duplicate volume number: 1"], project.volumes[1].warnings)
            self.assertEqual("Failed", project.volumes[1].status)
            self.assertIn("Source PDF not found", project.volumes[1].error)

    def test_export_ready_validates_and_skips_failed_volumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready_pdf = Path(tmp) / "Series Vol.01.pdf"
            missing_pdf = Path(tmp) / "Series Vol.02.pdf"
            output_dir = Path(tmp) / "out"
            ready_pdf.write_bytes(_two_page_pdf_with_late_cover())
            project = SeriesProject.from_pdfs([ready_pdf], title="Series")
            project.volumes[0].status = "Ready"
            project.volumes.append(
                type(project.volumes[0])(
                    pdf_path=missing_pdf,
                    volume_number=2,
                    status="Ready",
                )
            )

            summary = project.export_ready(output_dir)

            self.assertEqual({"exported": 1, "failed": 1, "skipped": 0, "warnings": 0}, summary)
            self.assertTrue((output_dir / "Series Vol.01.epub").exists())
            self.assertEqual("Exported", project.volumes[0].status)
            self.assertEqual("Failed", project.volumes[1].status)
            self.assertIn("Source PDF not found", project.volumes[1].error)


if __name__ == "__main__":
    unittest.main()
