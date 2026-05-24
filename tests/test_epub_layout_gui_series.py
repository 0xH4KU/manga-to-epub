import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from manga_pdf_to_epub.gui.layout_app import EpubLayoutApp

from tests.gui_helpers import (
    FakeDeleteModel,
    FakeListbox,
    FakeRoot,
    FakeStatus,
    FakeWidget,
    entry,
)


class EpubLayoutGuiSeriesTests(unittest.TestCase):
    def test_import_series_reveals_series_navigation(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_pane = FakeWidget()
        app.spine_pane = FakeWidget()
        app.series_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_workspace_status = lambda: None

        with patch(
            "manga_pdf_to_epub.gui.layout_series_project_controller.filedialog.askopenfilenames",
            return_value=("/tmp/[晚安,布布][淺野一二O] Vol.02.pdf", "/tmp/[晚安,布布][淺野一二O] Vol.01.pdf"),
        ):
            app.import_series()

        self.assertTrue(app.series_pane.packed)
        self.assertTrue(app.spine_pane.packed)

    def test_import_series_creates_project_and_populates_volume_list(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_list = FakeListbox(selection=0)
        app.series_pane = FakeWidget()
        app.spine_pane = FakeWidget()
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_workspace_status = lambda: None

        with patch(
            "manga_pdf_to_epub.gui.layout_series_project_controller.filedialog.askopenfilenames",
            return_value=("/tmp/[晚安,布布][淺野一二O] Vol.02.pdf", "/tmp/[晚安,布布][淺野一二O] Vol.01.pdf"),
        ):
            app.import_series()

        self.assertEqual("晚安,布布", app.series_project.title)
        self.assertEqual("淺野一二O", app.series_project.author)
        self.assertTrue(app.metadata_loaded)
        self.assertEqual(
            [
                "Unreviewed Vol.01 [晚安,布布][淺野一二O] Vol.01.pdf",
                "Unreviewed Vol.02 [晚安,布布][淺野一二O] Vol.02.pdf",
            ],
            app.series_list.items,
        )
        self.assertEqual("Imported series with 2 volumes.", app.status.value)

    def test_import_series_accepts_pdf_cbz_and_zip_sources(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_list = FakeListbox(selection=0)
        app.series_pane = FakeWidget()
        app.spine_pane = FakeWidget()
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app._load_metadata_fields = lambda: None
        app.refresh_workspace_status = lambda: None

        with patch(
            "manga_pdf_to_epub.gui.layout_series_project_controller.filedialog.askopenfilenames",
            return_value=("/tmp/Series Vol.01.cbz", "/tmp/Series Vol.02.zip"),
        ) as dialog:
            app.import_series()

        self.assertEqual([Path("/tmp/Series Vol.01.cbz"), Path("/tmp/Series Vol.02.zip")], [volume.pdf_path for volume in app.series_project.volumes])
        self.assertEqual("Import Series Sources", dialog.call_args.kwargs["title"])
        self.assertIn("*.pdf *.cbz *.zip", dialog.call_args.kwargs["filetypes"][0][1])

    def test_select_series_volume_loads_existing_editor_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        first = SimpleNamespace(
            pdf_path=Path("/tmp/vol01.pdf"),
            volume_number=1,
            status="Unreviewed",
            layout_model=FakeDeleteModel([entry("Page 1")]),
        )
        project = SimpleNamespace(
            volumes=[first],
            generated_title=lambda volume: f"Series Vol.{volume.volume_number:02d}",
            model_for_volume=lambda volume: volume.layout_model,
        )
        app.series_project = project
        app.series_list = FakeListbox(selection=0)
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.deleted_entries = []
        app.thumbnail_cache = {}
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_spine_views = lambda: setattr(app, "list_refreshed", True)
        app.refresh_preview_views = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_workspace_status = lambda: None

        app.select_series_volume()

        self.assertIs(first.layout_model, app.model)
        self.assertEqual(Path("/tmp/vol01.pdf"), app.pdf_path)
        self.assertIs(first, app.active_series_volume)
        self.assertTrue(app.metadata_loaded)
        self.assertTrue(app.list_refreshed)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Loaded Series Vol.01.", app.status.value)

    def test_select_series_volume_resets_diagnosis_for_loaded_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        first = SimpleNamespace(
            pdf_path=Path("/tmp/vol01.pdf"),
            volume_number=1,
            status="Unreviewed",
            layout_model=FakeDeleteModel([entry("Page 1"), entry("Page 2"), entry("Page 3")]),
        )
        project = SimpleNamespace(
            volumes=[first],
            generated_title=lambda volume: f"Series Vol.{volume.volume_number:02d}",
            model_for_volume=lambda volume: volume.layout_model,
        )
        app.series_project = project
        app.series_list = FakeListbox(selection=0)
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.deleted_entries = []
        app.thumbnail_cache = {}
        app.diagnosis_session = SimpleNamespace(source_page_count=99)
        app.spread_damage = ["old"]
        app.insert_classification = "old"
        app.diagnosis_stale = True
        app.diagnosis_panel = None
        app._load_metadata_fields = lambda: None
        app.refresh_spine_views = lambda: None
        app.refresh_preview_views = lambda: None
        app.refresh_workspace_status = lambda: None

        app.select_series_volume()

        self.assertEqual(3, app.diagnosis_session.source_page_count)
        self.assertEqual([], app.spread_damage)
        self.assertIsNone(app.insert_classification)
        self.assertFalse(app.diagnosis_stale)

    def test_mark_selected_series_volume_ready_updates_series_list(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volume = SimpleNamespace(status="Edited", volume_number=1, pdf_path=Path("/tmp/vol01.pdf"))
        project = SimpleNamespace(
            volumes=[volume],
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.series_project = project
        app.series_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()

        self.assertEqual("Ready", volume.status)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Marked Vol.01 ready.", app.status.value)

    def test_mark_selected_series_volume_ready_updates_all_selected_volumes(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volumes = [
            SimpleNamespace(status="Edited", volume_number=1, pdf_path=Path("/tmp/vol01.pdf")),
            SimpleNamespace(status="Edited", volume_number=2, pdf_path=Path("/tmp/vol02.pdf")),
            SimpleNamespace(status="Unreviewed", volume_number=7, pdf_path=Path("/tmp/vol07.pdf")),
        ]
        project = SimpleNamespace(
            volumes=volumes,
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.series_project = project
        app.series_list = FakeListbox(selection=(0, 1, 2))
        app.status = FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()

        self.assertEqual(["Ready", "Ready", "Ready"], [volume.status for volume in volumes])
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Marked 3 volumes ready.", app.status.value)

    def test_unready_selected_restores_only_selected_volume_status(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volumes = [
            SimpleNamespace(status="Edited", volume_number=index + 1, pdf_path=Path(f"/tmp/vol{index + 1:02d}.pdf"))
            for index in range(13)
        ]
        volumes[6].status = "Unreviewed"
        project = SimpleNamespace(
            volumes=volumes,
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.series_project = project
        app.series_list = FakeListbox(selection=tuple(range(13)))
        app.status = FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()
        app.series_list.selection = (6,)
        restored = app.unready_selected()

        self.assertTrue(restored)
        self.assertEqual("Unreviewed", volumes[6].status)
        self.assertEqual(["Ready"] * 12, [volume.status for index, volume in enumerate(volumes) if index != 6])
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Restored Vol.07 status.", app.status.value)

    def test_unready_selected_without_selection_restores_latest_ready_batch(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volumes = [
            SimpleNamespace(status="Edited", volume_number=1, pdf_path=Path("/tmp/vol01.pdf")),
            SimpleNamespace(status="Unreviewed", volume_number=2, pdf_path=Path("/tmp/vol02.pdf")),
        ]
        project = SimpleNamespace(
            volumes=volumes,
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.series_project = project
        app.series_list = FakeListbox(selection=(0, 1))
        app.status = FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()
        app.series_list.selection = None
        app.unready_selected()

        self.assertEqual(["Edited", "Unreviewed"], [volume.status for volume in volumes])
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Restored 2 volume statuses.", app.status.value)

    def test_recover_last_deleted_falls_back_to_unready_selected(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volume = SimpleNamespace(status="Edited", volume_number=1, pdf_path=Path("/tmp/vol01.pdf"))
        project = SimpleNamespace(
            volumes=[volume],
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.model = FakeDeleteModel([entry("Page 1")])
        app.deleted_entries = []
        app.series_project = project
        app.series_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()
        app.recover_last_deleted()

        self.assertEqual("Edited", volume.status)
        self.assertEqual("Restored Vol.01 status.", app.status.value)

    def test_unready_selected_without_history_is_noop(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()

        restored = app.unready_selected()

        self.assertFalse(restored)
        self.assertIsNone(app.status.value)

    def test_unready_selected_with_unmatched_selection_keeps_ready_history(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volumes = [
            SimpleNamespace(status="Edited", volume_number=1, pdf_path=Path("/tmp/vol01.pdf")),
            SimpleNamespace(status="Edited", volume_number=2, pdf_path=Path("/tmp/vol02.pdf")),
        ]
        project = SimpleNamespace(
            volumes=volumes,
            mark_ready=lambda selected: setattr(selected, "status", "Ready"),
        )
        app.series_project = project
        app.series_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.mark_selected_series_volume_ready()
        app.series_list.selection = (1,)
        restored = app.unready_selected()

        self.assertFalse(restored)
        self.assertEqual(["Ready", "Edited"], [volume.status for volume in volumes])
        self.assertEqual("No selected ready marks to undo.", app.status.value)
        self.assertEqual(1, len(app.ready_status_undo))

    def test_export_ready_series_uses_series_project(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)
        app.root = FakeRoot()
        events = [{"status": "summary", "exported": 1, "failed": 0, "skipped": 2, "warnings": 3}]
        project = SimpleNamespace(
            exported_to=None,
            volumes=[],
            validate_ready=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 0},
            export_ready_iter=lambda output_dir: setattr(project, "exported_to", output_dir) or iter(events),
        )
        app.series_project = project
        app._run_background = lambda _status, work, on_success: on_success(work()) or True

        with patch("manga_pdf_to_epub.gui.layout_series_export_controller.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        self.assertEqual(Path("/tmp/out"), project.exported_to)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Series exported 1 volumes; 0 failed, 2 skipped, 3 warnings.", app.status.value)

    def test_export_ready_series_stores_metadata_fields_before_exporting(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.refresh_series_list = lambda: None
        app.refresh_workspace_status = lambda: None
        app.root = FakeRoot()
        events = [{"status": "summary", "exported": 0, "failed": 0, "skipped": 0, "warnings": 0}]
        project = SimpleNamespace(
            volumes=[],
            validate_ready=lambda output_dir: {"ready": 0, "failed": 0, "warnings": 0},
            export_ready_iter=lambda output_dir: iter(events),
        )
        app.series_project = project
        app._store_metadata_fields = lambda: setattr(app, "metadata_stored", True)
        app._run_background = lambda _status, work, on_success: on_success(work()) or True

        with patch("manga_pdf_to_epub.gui.layout_series_export_controller.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        self.assertTrue(app.metadata_stored)

    def test_export_ready_series_runs_in_background(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.refresh_series_list = lambda: None
        app.refresh_workspace_status = lambda: None
        app.root = FakeRoot()
        events = [{"status": "summary", "exported": 1, "failed": 0, "skipped": 0, "warnings": 0}]
        project = SimpleNamespace(
            volumes=[],
            validate_ready=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 0},
            export_ready_iter=lambda output_dir: iter(events),
        )
        app.series_project = project
        app._run_background = lambda status, work, on_success: setattr(app, "background_call", (status, work, on_success)) or True

        with patch("manga_pdf_to_epub.gui.layout_series_export_controller.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        self.assertEqual("Exporting ready series...", app.background_call[0])
        self.assertEqual({"exported": 1, "failed": 0, "skipped": 0, "warnings": 0}, app.background_call[1]())

    def test_export_ready_series_background_work_consumes_progress_events(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.status = FakeStatus()
        app.refresh_series_list = lambda: setattr(app, "series_refresh_count", getattr(app, "series_refresh_count", 0) + 1)
        app.refresh_workspace_status = lambda: None
        app._open_series_export_progress = lambda: setattr(app, "progress_opened", True)
        app._finish_series_export_progress = lambda summary: setattr(app, "finished_summary", summary)
        events = [
            {"volume_number": 1, "status": "started", "output_path": Path("/tmp/out/Series Vol.01.epub")},
            {"volume_number": 1, "status": "exported", "output_path": Path("/tmp/out/Series Vol.01.epub")},
            {"status": "summary", "exported": 1, "failed": 0, "skipped": 0, "warnings": 0},
        ]
        project = SimpleNamespace(
            volumes=[],
            validate_ready=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 0},
            export_ready_iter=lambda output_dir: iter(events),
        )
        app.series_project = project
        app._run_background = lambda status, work, on_success: setattr(app, "background_call", (status, work, on_success)) or True

        with patch("manga_pdf_to_epub.gui.layout_series_export_controller.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        summary = app.background_call[1]()

        self.assertEqual({"exported": 1, "failed": 0, "skipped": 0, "warnings": 0}, summary)
        self.assertEqual("Exported Vol.01.", app.status.value)
        self.assertEqual(1, app.series_refresh_count)

    def test_series_export_opens_and_finishes_progress_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.refresh_series_list = lambda: None
        app.refresh_workspace_status = lambda: None
        app.root = FakeRoot()
        events = [{"status": "summary", "exported": 1, "failed": 0, "skipped": 0, "warnings": 0}]
        app.series_project = SimpleNamespace(
            volumes=[],
            validate_ready=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 0},
            export_ready_iter=lambda output_dir: iter(events),
        )
        app._run_background = lambda status, work, on_success: setattr(app, "background_call", (status, work, on_success)) or True

        with patch("manga_pdf_to_epub.gui.layout_series_export_controller.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        self.assertEqual("Exporting ready series...", app.series_export_progress["current"])
        app.background_call[2](app.background_call[1]())
        self.assertEqual("Close", app.series_export_progress["close_text"])
        self.assertEqual("1 exported, 0 failed, 0 skipped, 0 warnings", app.series_export_progress["summary"])

    def test_series_export_progress_reports_started_volume(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.series_export_progress = {}

        app._series_export_progress({"volume_number": 2, "status": "started"})

        self.assertEqual("Exporting Vol.02.", app.status.value)
        self.assertEqual("Exporting Vol.02.", app.series_export_progress["current"])

    def test_export_ready_series_busy_state_blocks_second_export(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.series_project = SimpleNamespace(export_ready_iter=lambda output_dir: iter([]))
        app._busy = True

        with patch("manga_pdf_to_epub.gui.layout_series_export_controller.filedialog.askdirectory", return_value="/tmp/out"):
            app.export_ready_series()

        self.assertEqual("Another operation is already running.", app.status.value)

    def test_export_ready_series_shows_warning_summary_before_background_export(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.root = FakeRoot()
        app.output_dir = Path("/tmp")
        volume = SimpleNamespace(volume_number=1, status="Ready", warnings=["check page count"], error=None)
        project = SimpleNamespace(
            volumes=[volume],
            validate_ready=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 1},
            export_ready_iter=lambda output_dir: iter([{"status": "summary", "exported": 1, "failed": 0, "skipped": 0, "warnings": 1}]),
        )
        app.series_project = project
        app._run_background = lambda status, work, on_success: setattr(app, "background_call", (status, work, on_success)) or True
        app._open_series_export_progress = lambda: setattr(app, "progress_opened", True)

        with patch("manga_pdf_to_epub.gui.layout_series_export_controller.filedialog.askdirectory", return_value="/tmp/out"):
            with patch("manga_pdf_to_epub.gui.layout_series_export_controller.messagebox.showwarning") as showwarning:
                app.export_ready_series()

        showwarning.assert_called_once()
        self.assertIn("Vol.01: check page count", showwarning.call_args.args[1])
        self.assertTrue(app.progress_opened)
        self.assertEqual("Exporting ready series...", app.background_call[0])

if __name__ == "__main__":
    unittest.main()
