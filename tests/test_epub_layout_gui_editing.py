import unittest
from unittest.mock import patch
from types import SimpleNamespace

from manga_pdf_to_epub.gui.layout_app import EpubLayoutApp
from manga_pdf_to_epub.gui.layout_history import CoverState, DeleteHistory

from tests.gui_helpers import (
    FakeDeleteModel,
    FakeListbox,
    FakeStatus,
    entry,
    inserted_entry,
)


class EpubLayoutGuiEditingTests(unittest.TestCase):
    def test_delete_selected_entry_uses_common_delete_for_blank(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Blank 1", is_blank=True), entry("Page 1")])
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.delete_selected_entry()

        self.assertEqual([0], app.model.deleted)
        self.assertEqual([[(0, "Blank 1")]], [[(index, entry.label) for index, entry in group] for group in app.deleted_entries])
        self.assertEqual(0, app.page_list.selection)
        self.assertTrue(app.preserved_yview)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Removed Blank 1 from layout.", app.status.value)

    def test_insert_blank_marks_active_series_volume_edited(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1")])
        volume = SimpleNamespace(status="Unreviewed", volume_number=1)
        app.active_series_volume = volume
        app.series_project = SimpleNamespace(volumes=[volume])
        app.series_list = FakeListbox(selection=0)
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.insert_blank(before=False)

        self.assertEqual("Edited", volume.status)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)

    def test_insert_blank_in_single_pdf_mode_does_not_require_series_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1")])
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.insert_blank(before=False)

        self.assertEqual(["Page 1", "Blank 2"], [entry.label for entry in app.model.entries])
        self.assertFalse(hasattr(app, "series_refreshed"))

    def test_quick_blank_before_cover_uses_selected_cover_position(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2"), entry("Page 3")])
        app.model.cover_source_index = 3
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.quick_blank_before_cover()

        self.assertEqual(["Page 1", "Page 2", "Blank 3", "Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual(2, app.page_list.selection)

    def test_quick_blank_after_cover_uses_selected_cover_position(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2"), entry("Page 3")])
        app.model.cover_source_index = 2
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.quick_blank_after_cover()

        self.assertEqual(["Page 1", "Page 2", "Blank 3", "Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual(2, app.page_list.selection)

    def test_refresh_after_layout_edit_centralizes_selection_preview_and_edit_state(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
        volume = SimpleNamespace(status="Ready", volume_number=1)
        app.active_series_volume = volume
        app.series_project = SimpleNamespace(volumes=[volume])
        app.series_list = FakeListbox(selection=0)
        app.page_list = FakeListbox(selection=0)
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app._refresh_after_layout_edit(select_index=1)

        self.assertTrue(app.preserved_yview)
        self.assertEqual(1, app.page_list.selection)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Edited", volume.status)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)

    def test_layout_edit_marks_diagnosis_stale_and_clears_markers(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
        app.page_list = FakeListbox(selection=0)
        app.spine_markers = {0: object()}
        app.insert_classification = object()
        app.diagnosis_stale = False
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)
        app.refresh_diagnosis_panel = lambda: setattr(app, "diagnosis_refreshed", True)

        app._refresh_after_layout_edit(select_index=1)

        self.assertTrue(app.diagnosis_stale)
        self.assertIsNone(app.insert_classification)
        self.assertEqual({}, app.spine_markers)
        self.assertTrue(app.diagnosis_refreshed)

    def test_set_selected_as_cover_marks_ready_series_volume_edited(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
        volume = SimpleNamespace(status="Ready", volume_number=1)
        app.active_series_volume = volume
        app.series_project = SimpleNamespace(volumes=[volume])
        app.series_list = FakeListbox(selection=0)
        app.page_list = FakeListbox(selection=1)
        app.status = FakeStatus()
        app.refresh_spine_views = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_series_list = lambda: setattr(app, "series_refreshed", True)
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)

        app.set_selected_as_cover()

        self.assertEqual("Edited", volume.status)
        self.assertTrue(app.series_refreshed)
        self.assertTrue(app.workspace_refreshed)

    def test_delete_selected_entry_confirms_real_pages(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
        app.page_list = FakeListbox(selection=1)
        app.status = FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("manga_pdf_to_epub.gui.layout_delete_controller.messagebox.askyesno", return_value=True) as askyesno:
            app.delete_selected_entry()

        askyesno.assert_called_once()
        self.assertEqual([1], app.model.deleted)
        self.assertEqual(0, app.page_list.selection)
        self.assertTrue(app.preserved_yview)

    def test_recover_last_deleted_restoresentry_to_original_position(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        page_1 = entry("Page 1")
        page_2 = entry("Page 2")
        page_3 = entry("Page 3")
        app.model = FakeDeleteModel([page_1, page_3])
        app.deleted_entries = [[(1, page_2)]]
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.recover_last_deleted()

        self.assertEqual(["Page 1", "Page 2", "Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual([], app.deleted_entries)
        self.assertEqual(1, app.page_list.selection)
        self.assertTrue(app.preserved_yview)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Recovered Page 2 at position 2.", app.status.value)

    def test_recover_last_deleted_is_lifo_and_clamps_position(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        page_1 = entry("Page 1")
        page_2 = entry("Page 2")
        page_9 = entry("Page 9")
        app.model = FakeDeleteModel([page_1])
        app.deleted_entries = [[(1, page_2)], [(8, page_9)]]
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: None
        app.refresh_preview = lambda: None

        app.recover_last_deleted()

        self.assertEqual(["Page 1", "Page 9"], [entry.label for entry in app.model.entries])
        self.assertEqual([[(1, "Page 2")]], [[(index, entry.label) for index, entry in group] for group in app.deleted_entries])
        self.assertEqual(1, app.page_list.selection)

    def test_quick_delete_first_records_one_undo_group(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2"), entry("Page 3")])
        app.page_list = FakeListbox(selection=2)
        app.status = FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("manga_pdf_to_epub.gui.layout_delete_controller.messagebox.askyesno", return_value=True):
            app.quick_delete_first(2)

        self.assertEqual(["Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual([[(0, "Page 1"), (1, "Page 2")]], [[(index, entry.label) for index, entry in group] for group in app.deleted_entries])
        self.assertEqual(0, app.page_list.selection)
        self.assertEqual("Deleted 2 entries: 2 images, 0 blanks.", app.status.value)

    def test_cancelled_group_delete_restores_cover_selection(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2"), entry("Page 3")])
        app.model.cover_source_index = 2
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("manga_pdf_to_epub.gui.layout_delete_controller.messagebox.askyesno", return_value=False):
            app.quick_delete_first(2)

        self.assertEqual(["Page 1", "Page 2", "Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual(2, app.model.cover_source_index)
        self.assertEqual([], app.deleted_entries)

    def test_recover_last_deleted_restores_grouped_delete(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        page_1 = entry("Page 1")
        page_2 = entry("Page 2")
        page_3 = entry("Page 3")
        app.model = FakeDeleteModel([page_3])
        app.deleted_entries = [[(0, page_1), (1, page_2)]]
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.recover_last_deleted()

        self.assertEqual(["Page 1", "Page 2", "Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual([], app.deleted_entries)
        self.assertEqual(0, app.page_list.selection)
        self.assertEqual("Recovered 2 pages.", app.status.value)

    def test_recover_last_deleted_restores_cover_selection(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        page_1 = entry("Page 1")
        page_2 = entry("Page 2")
        app.model = FakeDeleteModel([page_1])
        app.model.cover_source_index = 1
        app.deleted_history = DeleteHistory()
        app.deleted_history.push([(1, page_2)], CoverState(2, None))
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.recover_last_deleted()

        self.assertEqual(2, app.model.cover_source_index)

    def test_set_selected_as_cover_updates_model_and_status(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
        app.page_list = FakeListbox(selection=1)
        app.status = FakeStatus()
        app.refresh_spine_views = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)

        app.set_selected_as_cover()

        self.assertEqual(2, app.model.cover_source_index)
        self.assertTrue(app.preserved_yview)
        self.assertEqual("Set Page 2 as cover.", app.status.value)

    def test_set_selected_as_cover_accepts_inserted_images(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        inserted = inserted_entry("Extra Cover")
        app.model = FakeDeleteModel([entry("Page 1"), inserted])
        app.model.set_cover_entry = lambda entry: setattr(app, "cover_entry", entry)
        app.page_list = FakeListbox(selection=1)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)

        app.set_selected_as_cover()

        self.assertIs(inserted, app.cover_entry)
        self.assertTrue(app.preserved_yview)
        self.assertEqual("Set Extra Cover as cover.", app.status.value)

    def test_set_selected_as_cover_rejects_blank_pages(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Blank 1", is_blank=True)])
        app.page_list = FakeListbox(selection=1)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)

        with patch("manga_pdf_to_epub.gui.layout_cover_controller.messagebox.showerror") as showerror:
            app.set_selected_as_cover()

        showerror.assert_called_once_with("Set cover failed", "Cover must be an image page.")
        self.assertEqual(1, app.model.cover_source_index)
        self.assertFalse(hasattr(app, "preserved_yview"))

    def test_selected_indexes_support_multi_selection(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.page_list = FakeListbox(selection=None)
        app.page_list.curselection = lambda: (0, 2)

        self.assertEqual([0, 2], app.selected_indexes())

    def test_drag_release_moves_pressed_row_to_target_row(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2"), entry("Page 3")])
        app.page_list = FakeListbox(selection=0)
        app.page_list.items = ["Page 1", "Page 2", "Page 3"]
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app.series_project = None
        app._page_drag_source = None
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app._page_drag_start(SimpleNamespace(y=0))
        app._page_drag_release(SimpleNamespace(y=2))

        self.assertEqual(["Page 2", "Page 3", "Page 1"], [entry.label for entry in app.model.entries])
        self.assertEqual(2, app.page_list.selection)
        self.assertTrue(app.preview_refreshed)
        self.assertEqual("Moved Page 1 to position 3.", app.status.value)

    def test_drag_release_on_same_row_does_not_move(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2")])
        app.page_list = FakeListbox(selection=0)
        app.page_list.items = ["Page 1", "Page 2"]
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app.series_project = None
        app._page_drag_source = None
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app._page_drag_start(SimpleNamespace(y=1))
        app._page_drag_release(SimpleNamespace(y=1))

        self.assertEqual(["Page 1", "Page 2"], [entry.label for entry in app.model.entries])
        self.assertFalse(hasattr(app, "preview_refreshed"))
        self.assertIsNone(app.status.value)

    def test_drag_uses_pressed_row_when_selection_differs(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1"), entry("Page 2"), entry("Page 3")])
        app.page_list = FakeListbox(selection=0)
        app.page_list.items = ["Page 1", "Page 2", "Page 3"]
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app.series_project = None
        app._page_drag_source = None
        app.refresh_preview = lambda: None

        app._page_drag_start(SimpleNamespace(y=1))
        app._page_drag_release(SimpleNamespace(y=2))

        self.assertEqual(["Page 1", "Page 3", "Page 2"], [entry.label for entry in app.model.entries])
        self.assertEqual(2, app.page_list.selection)

    def test_insert_image_after_selected_page_calls_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Page 1")])
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("manga_pdf_to_epub.gui.layout_edit_controller.filedialog.askopenfilename", return_value="/tmp/extra.png"):
            app.insert_image(before=False)

        self.assertEqual(["Page 1", "Image 2"], [entry.label for entry in app.model.entries])
        self.assertTrue(app.preserved_yview)
        self.assertEqual("Inserted image: extra.png", app.status.value)

    def test_hidden_legacy_gui_actions_are_removed(self):
        removed_method_names = (
            "normalize" + "_export_order",
            "use_current_layout_as" + "_batch_template",
            "load_batch_template" + "_from_preset",
            "add_batch" + "_pdfs",
            "validate" + "_batch",
            "export_ready" + "_batch",
            "export_all" + "_batch",
        )
        for method_name in removed_method_names:
            self.assertFalse(hasattr(EpubLayoutApp, method_name), method_name)

    def test_quick_delete_status_reports_deleted_mix(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = FakeDeleteModel([entry("Blank 1", is_blank=True), entry("Page 1"), entry("Page 2")])
        app.page_list = FakeListbox(selection=0)
        app.status = FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("manga_pdf_to_epub.gui.layout_delete_controller.messagebox.askyesno", return_value=True):
            app.quick_delete_first(2)

        self.assertEqual("Deleted 2 entries: 1 image, 1 blank.", app.status.value)

if __name__ == "__main__":
    unittest.main()
