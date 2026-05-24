import unittest
import json
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from manga_pdf_to_epub.gui.layout_app import EpubLayoutApp

from tests.gui_helpers import (
    FakeBool,
    FakeDeleteModel,
    FakeListbox,
    FakePresetModel,
    FakeStatus,
    FakeWidget,
    entry,
)


class EpubLayoutGuiProjectTests(unittest.TestCase):
    def test_store_metadata_fields_updates_cover_only_option(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
        app.series_project = None
        app.title_var = SimpleNamespace(get=lambda: "Book")
        app.author_var = SimpleNamespace(get=lambda: "")
        app.language_var = SimpleNamespace(get=lambda: "zh-Hant")
        app.exclude_cover_var = FakeBool(True)

        app._store_metadata_fields()

        self.assertTrue(app.model.exclude_cover_from_reading)

    def test_store_metadata_fields_updates_series_metadata_in_series_mode(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1")])
        app.model.source_path = Path("/tmp/[晚安,布布][淺野一二O] Vol.01.pdf")
        app.model.title = "晚安,布布 Vol.01"
        app.model.author = "淺野一二O"
        app.model.language = "ja"
        app.model.exclude_cover_from_reading = False
        app.series_project = SimpleNamespace(title="Old", author="", language="zh-Hant")
        app.title_var = SimpleNamespace(get=lambda: "晚安,布布")
        app.author_var = SimpleNamespace(get=lambda: "淺野一二O")
        app.language_var = SimpleNamespace(get=lambda: "ja")
        app.exclude_cover_var = FakeBool(True)

        app._store_metadata_fields()

        self.assertEqual("晚安,布布", app.series_project.title)
        self.assertEqual("淺野一二O", app.series_project.author)
        self.assertEqual("ja", app.series_project.language)
        self.assertEqual("晚安,布布 Vol.01", app.model.title)
        self.assertTrue(app.model.exclude_cover_from_reading)

    def test_load_metadata_fields_reads_cover_only_option(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
        app.model.title = "Book"
        app.model.author = ""
        app.model.language = "zh-Hant"
        app.model.exclude_cover_from_reading = True
        app.series_project = None
        app.title_var = SimpleNamespace(set=lambda value: setattr(app, "title_value", value))
        app.author_var = SimpleNamespace(set=lambda value: setattr(app, "author_value", value))
        app.language_var = SimpleNamespace(set=lambda value: setattr(app, "language_value", value))
        app.exclude_cover_var = FakeBool(False)

        app._load_metadata_fields()

        self.assertTrue(app.exclude_cover_var.get())

    def test_load_metadata_fields_reads_series_metadata_in_series_mode(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1")])
        app.model.title = "晚安,布布 Vol.01"
        app.model.author = "淺野一二O"
        app.model.language = "ja"
        app.model.exclude_cover_from_reading = True
        app.series_project = SimpleNamespace(title="晚安,布布", author="淺野一二O", language="ja")
        app.title_var = SimpleNamespace(set=lambda value: setattr(app, "title_value", value))
        app.author_var = SimpleNamespace(set=lambda value: setattr(app, "author_value", value))
        app.language_var = SimpleNamespace(set=lambda value: setattr(app, "language_value", value))
        app.exclude_cover_var = FakeBool(False)

        app._load_metadata_fields()

        self.assertEqual("晚安,布布", app.title_value)
        self.assertEqual("淺野一二O", app.author_value)
        self.assertEqual("ja", app.language_value)
        self.assertTrue(app.exclude_cover_var.get())

    def test_load_preset_single_pdf_mode_applies_to_current_model_without_scope_prompt(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakePresetModel([entry("Page 1")])
        app.series_project = None
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.spine_markers = {0: object()}
        app.insert_classification = object()
        app.diagnosis_stale = False
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_spine_views = lambda: setattr(app, "list_refreshed", True)
        app.refresh_preview_views = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_diagnosis_panel = lambda: setattr(app, "diagnosis_refreshed", True)

        with patch("manga_pdf_to_epub.gui.layout_app.filedialog.askopenfilename", return_value="/tmp/layout.json"), \
            patch("manga_pdf_to_epub.gui.layout_app.simpledialog.askstring") as askstring:
            app.load_preset()

        self.assertEqual([Path("/tmp/layout.json")], app.model.applied_presets)
        askstring.assert_not_called()
        self.assertTrue(app.diagnosis_stale)
        self.assertIsNone(app.insert_classification)
        self.assertEqual({}, app.spine_markers)
        self.assertTrue(app.diagnosis_refreshed)
        self.assertEqual("Loaded preset: layout.json", app.status.value)

    def test_load_preset_series_mode_prompts_scope_and_applies_to_matching_volumes(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        active_model = FakePresetModel([entry("Page 1")])
        inactive_model = FakePresetModel([entry("Page 1")])
        volumes = [
            SimpleNamespace(volume_number=1, status="Ready", layout_model=active_model),
            SimpleNamespace(volume_number=2, status="Unreviewed", layout_model=inactive_model),
            SimpleNamespace(volume_number=7, status="Unreviewed", layout_model=FakePresetModel([entry("Page 1")])),
        ]
        project = SimpleNamespace(
            volumes=volumes,
            model_for_volume=lambda volume: volume.layout_model,
            volumes_for_scope=lambda scope: [volumes[0], volumes[2]] if scope == "1,7" else [],
            generated_title=lambda volume: f"Series Vol.{volume.volume_number:02d}",
            title="Series",
            author="Author",
            language="ja",
        )
        app.model = active_model
        app.series_project = project
        app.active_series_volume = volumes[0]
        app.series_list = FakeListbox(selection=0)
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.spine_markers = {0: object()}
        app.insert_classification = object()
        app.diagnosis_stale = False
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_spine_views = lambda: setattr(app, "list_refreshed", True)
        app.refresh_preview_views = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)
        app.refresh_diagnosis_panel = lambda: setattr(app, "diagnosis_refreshed", True)

        with patch("manga_pdf_to_epub.gui.layout_app.filedialog.askopenfilename", return_value="/tmp/layout.json"), \
            patch("manga_pdf_to_epub.gui.layout_app.simpledialog.askstring", return_value="1,7"):
            app.load_preset()

        self.assertEqual([Path("/tmp/layout.json")], volumes[0].layout_model.applied_presets)
        self.assertEqual([], volumes[1].layout_model.applied_presets)
        self.assertEqual([Path("/tmp/layout.json")], volumes[2].layout_model.applied_presets)
        self.assertEqual(["Edited", "Unreviewed", "Edited"], [volume.status for volume in volumes])
        self.assertTrue(app.list_refreshed)
        self.assertTrue(app.preview_refreshed)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.diagnosis_stale)
        self.assertIsNone(app.insert_classification)
        self.assertEqual({}, app.spine_markers)
        self.assertTrue(app.diagnosis_refreshed)
        self.assertEqual("Loaded preset for 2 volumes: layout.json", app.status.value)

    def test_load_preset_series_mode_cancels_when_scope_is_blank(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakePresetModel([entry("Page 1")])
        app.series_project = SimpleNamespace(volumes=[])
        app.status = FakeStatus()

        with patch("manga_pdf_to_epub.gui.layout_app.filedialog.askopenfilename", return_value="/tmp/layout.json"), \
            patch("manga_pdf_to_epub.gui.layout_app.simpledialog.askstring", return_value=""):
            app.load_preset()

        self.assertEqual([], app.model.applied_presets)
        self.assertIsNone(app.status.value)

    def test_save_project_writes_series_project_payload(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.model = FakeDeleteModel([entry("Page 1")])
        app._store_metadata_fields = lambda: setattr(app, "metadata_stored", True)
        project = SimpleNamespace(to_payload=lambda project_path: {"version": 1, "path": str(project_path)})
        app.series_project = project

        with patch("manga_pdf_to_epub.gui.layout_series_controller.filedialog.asksaveasfilename", return_value="/tmp/series-project.json"):
            app.save_project()

        self.assertTrue(app.metadata_stored)
        self.assertEqual(
            {"version": 1, "path": "/tmp/series-project.json"},
            json.loads(Path("/tmp/series-project.json").read_text(encoding="utf-8")),
        )
        self.assertEqual("Saved project: series-project.json", app.status.value)
        Path("/tmp/series-project.json").unlink()

    def test_save_project_records_active_volume_number(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.model = None
        active = SimpleNamespace(volume_number=2)
        project = SimpleNamespace(
            active_volume_number=None,
            to_payload=lambda project_path: {"version": 1, "active": project.active_volume_number},
        )
        app.series_project = project
        app.active_series_volume = active

        with patch("manga_pdf_to_epub.gui.layout_series_controller.filedialog.asksaveasfilename", return_value="/tmp/active-series-project.json"):
            app.save_project()

        self.assertEqual(2, project.active_volume_number)
        Path("/tmp/active-series-project.json").unlink()

    def test_open_project_loads_series_project_and_refreshes_workspace(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_list = FakeListbox(selection=0)
        app.page_list = FakeListbox(selection=0)
        app.series_pane = FakeWidget()
        app.spine_pane = FakeWidget()
        app.status = FakeStatus()
        app.deleted_entries = ["old"]
        app.ready_status_undo = ["old"]
        app.thumbnail_cache = {"old": object()}
        app._load_metadata_fields = lambda: setattr(app, "metadata_loaded", True)
        app.refresh_spine_views = lambda: setattr(app, "list_refreshed", True)
        app.refresh_preview_views = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)
        payload_path = Path("/tmp/open-series-project.json")
        payload_path.write_text(json.dumps({"version": 1}), encoding="utf-8")
        volume = SimpleNamespace(pdf_path=Path("/tmp/vol01.pdf"), volume_number=1, status="Ready")
        loaded_project = SimpleNamespace(volumes=[volume], title="Series", author="", language="zh-Hant")

        with patch("manga_pdf_to_epub.gui.layout_series_controller.filedialog.askopenfilename", return_value=str(payload_path)), \
            patch("manga_pdf_to_epub.gui.layout_series_controller.SeriesProject.from_payload", return_value=loaded_project) as from_payload:
            app.open_project()

        from_payload.assert_called_once_with({"version": 1}, payload_path)
        self.assertIs(loaded_project, app.series_project)
        self.assertIsNone(app.model)
        self.assertIsNone(app.pdf_path)
        self.assertIsNone(app.active_series_volume)
        self.assertEqual([], app.deleted_entries)
        self.assertEqual([], app.ready_status_undo)
        self.assertEqual({}, app.thumbnail_cache)
        self.assertTrue(app.metadata_loaded)
        self.assertTrue(app.list_refreshed)
        self.assertTrue(app.preview_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual(["Ready Vol.01 vol01.pdf"], app.series_list.items)
        self.assertEqual("Opened project: open-series-project.json", app.status.value)
        payload_path.unlink()

    def test_open_project_refreshes_diagnose_views_for_empty_active_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_list = FakeListbox(selection=0)
        app.page_list = FakeListbox(selection=0)
        app.page_list.items = ["old main row"]
        app.diagnosis_window = SimpleNamespace(spine_list=FakeListbox(selection=0))
        app.diagnosis_window.spine_list.items = ["old diagnose row"]
        app.series_pane = FakeWidget()
        app.spine_pane = FakeWidget()
        app.status = FakeStatus()
        app.deleted_entries = []
        app.ready_status_undo = []
        app.thumbnail_cache = {}
        app._load_metadata_fields = lambda: None
        app.refresh_series_list = lambda: None
        app._restore_saved_active_series_selection = lambda: None
        app.refresh_preview_views = lambda: setattr(app, "preview_views_refreshed", True)
        app.refresh_workspace_status = lambda: None
        payload_path = Path("/tmp/open-series-project-empty-active.json")
        payload_path.write_text(json.dumps({"version": 1}), encoding="utf-8")
        loaded_project = SimpleNamespace(volumes=[], title="Series", author="", language="zh-Hant")

        with patch("manga_pdf_to_epub.gui.layout_series_controller.filedialog.askopenfilename", return_value=str(payload_path)), \
            patch("manga_pdf_to_epub.gui.layout_series_controller.SeriesProject.from_payload", return_value=loaded_project), \
            patch("manga_pdf_to_epub.gui.layout_series_controller.messagebox.showerror") as showerror:
            app.open_project()

        showerror.assert_not_called()
        self.assertEqual([], app.page_list.items)
        self.assertEqual([], app.diagnosis_window.spine_list.items)
        self.assertTrue(app.preview_views_refreshed)
        payload_path.unlink()

    def test_open_project_restores_active_series_selection_when_saved_volume_exists(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_list = FakeListbox(selection=0)
        app.page_list = FakeListbox(selection=0)
        app.series_pane = FakeWidget()
        app.spine_pane = FakeWidget()
        app.status = FakeStatus()
        app.deleted_entries = []
        app.ready_status_undo = []
        app.thumbnail_cache = {}
        app._load_metadata_fields = lambda: None
        app.refresh_spine_views = lambda: None
        app.refresh_preview_views = lambda: None
        app.refresh_workspace_status = lambda: None
        payload_path = Path("/tmp/open-active-series-project.json")
        payload_path.write_text(json.dumps({"version": 1}), encoding="utf-8")
        volumes = [
            SimpleNamespace(pdf_path=Path("/tmp/vol01.pdf"), volume_number=1, status="Ready"),
            SimpleNamespace(pdf_path=Path("/tmp/vol02.pdf"), volume_number=2, status="Edited"),
        ]
        loaded_project = SimpleNamespace(volumes=volumes, title="Series", author="", language="zh-Hant", active_volume_number=2)

        with patch("manga_pdf_to_epub.gui.layout_series_controller.filedialog.askopenfilename", return_value=str(payload_path)), \
            patch("manga_pdf_to_epub.gui.layout_series_controller.SeriesProject.from_payload", return_value=loaded_project):
            app.open_project()

        self.assertIs(volumes[1], app.active_series_volume)
        self.assertEqual(1, app.series_list.selection)
        payload_path.unlink()

    def test_load_series_volume_refreshes_open_diagnose_window_from_volume_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        volume = SimpleNamespace(pdf_path=Path("/tmp/vol02.pdf"), volume_number=2)
        model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
        app.series_project = SimpleNamespace(
            model_for_volume=lambda selected: model if selected is volume else None,
            generated_title=lambda selected: f"Series Vol.{selected.volume_number:02d}",
        )
        app.page_list = FakeListbox(selection=None)
        app.diagnosis_window = SimpleNamespace(
            spine_list=FakeListbox(selection=None),
            preview=SimpleNamespace(delete=lambda *_args: None, winfo_width=lambda: 400, winfo_height=lambda: 300),
            photo_refs=[],
        )
        app.diagnosis_window.spine_list.items = ["old row"]
        app._reset_deleted_history = lambda: None
        app._reset_preview_cache = lambda: None
        app._load_metadata_fields = lambda: None
        app.refresh_workspace_status = lambda: None
        app.refresh_preview = lambda: setattr(app, "main_preview_refreshed", True)
        app.refresh_diagnosis_preview = lambda: setattr(app, "diagnosis_preview_refreshed", True)
        app._is_cover_entry = lambda _entry: False
        app.apple_preview = FakeBool(False)
        app.status = FakeStatus()

        app._load_series_volume(volume)

        self.assertEqual(["0001 [page] Page 1", "0002 [page] Page 2"], app.diagnosis_window.spine_list.items)
        self.assertEqual(0, app.diagnosis_window.spine_list.selection)
        self.assertTrue(app.main_preview_refreshed)
        self.assertTrue(app.diagnosis_preview_refreshed)

    def test_validate_series_updates_warnings_and_status(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.output_dir = Path("/tmp")
        volume = SimpleNamespace(volume_number=1, status="Ready", warnings=["check"], error=None)
        project = SimpleNamespace(
            volumes=[volume],
            validate_all=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 1},
        )
        app.series_project = project
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        with patch("manga_pdf_to_epub.gui.layout_series_controller.messagebox.showwarning"):
            app.validate_series()

        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)
        self.assertEqual("Series validation: 1 ready, 0 failed, 1 warnings.", app.status.value)

    def test_validate_series_shows_warning_summary_dialog(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.status = FakeStatus()
        app.output_dir = Path("/tmp")
        volume = SimpleNamespace(volume_number=1, status="Ready", warnings=["check page count"], error=None)
        app.series_project = SimpleNamespace(
            volumes=[volume],
            validate_all=lambda output_dir: {"ready": 1, "failed": 0, "warnings": 1},
        )
        app.refresh_series_list = lambda: None
        app.refresh_workspace_status = lambda: None

        with patch("manga_pdf_to_epub.gui.layout_series_controller.messagebox.showwarning") as showwarning:
            app.validate_series()

        showwarning.assert_called_once()
        self.assertIn("Vol.01: check page count", showwarning.call_args.args[1])

if __name__ == "__main__":
    unittest.main()
