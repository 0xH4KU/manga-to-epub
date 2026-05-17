import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from epub_layout_gui import EpubLayoutApp


class _FakeBool:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _FakeCanvas:
    def delete(self, *_args):
        pass

    def winfo_width(self):
        return 400

    def winfo_height(self):
        return 300


class _FakeListbox:
    def __init__(self, selection=0, yview=(0.4, 0.7)):
        self.items = []
        self.selection = selection
        self.current_yview = yview
        self.moved_to = None

    def curselection(self):
        return () if self.selection is None else (self.selection,)

    def delete(self, *_args):
        self.items.clear()
        self.current_yview = (0.0, 0.0)

    def insert(self, _where, value):
        self.items.append(value)

    def selection_clear(self, *_args):
        self.selection = None

    def selection_set(self, index):
        self.selection = index

    def yview(self):
        return self.current_yview

    def yview_moveto(self, fraction):
        self.moved_to = fraction
        self.current_yview = (fraction, fraction)


class _FakeStatus:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class _FakeDeleteModel:
    def __init__(self, entries):
        self.entries = entries
        self.deleted = []
        self.cover_source_index = 1

    def delete_entry(self, index):
        self.deleted.append(index)
        del self.entries[index]

    def delete_first(self, count):
        deleted = []
        for offset in range(count):
            entry = self.entries.pop(0)
            deleted.append((offset, entry))
        return deleted

    def delete_last(self, count):
        start = len(self.entries) - count
        deleted = [(start + offset, entry) for offset, entry in enumerate(self.entries[start:])]
        del self.entries[start:]
        return deleted

    def delete_range(self, start, end):
        deleted = [(index, self.entries[index]) for index in range(start, end + 1)]
        del self.entries[start : end + 1]
        return deleted

    def set_cover(self, source_index):
        self.cover_source_index = source_index

    def insert_image(self, index, image_path):
        self.entries.insert(index, _entry(f"Image {index + 1}"))

    def export_selected_images(self, indexes, output_dir):
        return [output_dir / f"{index + 1:04d}.jpg" for index in indexes], 0


class _FakeBatchProject:
    def __init__(self):
        self.items = []
        self.validated_dir = None

    def add_pdf(self, path):
        item = SimpleNamespace(pdf_path=path, status="Pending", warnings=[], error=None)
        self.items.append(item)
        return item

    def validate_all(self, output_dir):
        self.validated_dir = output_dir
        for item in self.items:
            item.status = "Ready"

    def export_ready(self, output_dir):
        return {"exported": len(self.items), "failed": 0, "skipped": 0}


def _entry(label, is_blank=False):
    source_index = None if is_blank else int(label.split()[-1])
    return SimpleNamespace(label=label, is_blank=is_blank, source_index=source_index)


def _app_for_preview(entries, selected):
    app = EpubLayoutApp.__new__(EpubLayoutApp)
    app.preview = _FakeCanvas()
    app.photo_refs = []
    app.model = SimpleNamespace(entries=entries)
    app.apple_preview = _FakeBool(True)
    app.selected_index = lambda: selected
    app.draws = []
    app._draw_entry = lambda entry, x, y, width, height: app.draws.append((entry.label, x))
    return app


class EpubLayoutGuiPreviewTests(unittest.TestCase):
    def test_apple_cover_gap_is_drawn_on_right_of_cover(self):
        app = _app_for_preview([_entry("Page 1"), _entry("Page 2")], selected=0)

        app.refresh_preview()

        self.assertEqual(
            [("Page 1", 12), ("Virtual Apple Books cover gap", 206)],
            app.draws,
        )

    def test_selected_pages_after_cover_map_past_virtual_apple_gap(self):
        app = _app_for_preview([_entry("Page 1"), _entry("Page 2"), _entry("Page 3")], selected=1)

        app.refresh_preview()

        self.assertEqual(
            [("Page 2", 206), ("Page 3", 12)],
            app.draws,
        )

    def test_blank_before_cover_does_not_remove_virtual_apple_gap(self):
        app = _app_for_preview([_entry("Blank 1", is_blank=True), _entry("Page 1"), _entry("Page 2")], selected=0)

        app.refresh_preview()

        self.assertEqual(
            [("Blank 1", 12), ("Virtual Apple Books cover gap", 206)],
            app.draws,
        )

    def test_cover_after_inserted_blank_maps_past_virtual_apple_gap(self):
        app = _app_for_preview([_entry("Blank 1", is_blank=True), _entry("Page 1"), _entry("Page 2")], selected=1)

        app.refresh_preview()

        self.assertEqual(
            [("Page 1", 206), ("Page 2", 12)],
            app.draws,
        )


class EpubLayoutGuiListTests(unittest.TestCase):
    def test_refresh_list_can_preserve_scroll_position(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = SimpleNamespace(entries=[_entry(f"Page {index}") for index in range(1, 8)])
        app.page_list = _FakeListbox(yview=(0.5, 0.8))

        app.refresh_list(preserve_yview=True)

        self.assertEqual(0.5, app.page_list.moved_to)

    def test_refresh_list_marks_cover_entry(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.model.cover_source_index = 2
        app.page_list = _FakeListbox(yview=(0.5, 0.8))

        app.refresh_list()

        self.assertEqual("0002 [page] [cover] Page 2", app.page_list.items[1])

    def test_delete_selected_entry_uses_common_delete_for_blank(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Blank 1", is_blank=True), _entry("Page 1")])
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
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

    def test_delete_selected_entry_confirms_real_pages(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.page_list = _FakeListbox(selection=1)
        app.status = _FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("epub_layout_gui.messagebox.askyesno", return_value=True) as askyesno:
            app.delete_selected_entry()

        askyesno.assert_called_once()
        self.assertEqual([1], app.model.deleted)
        self.assertEqual(0, app.page_list.selection)
        self.assertTrue(app.preserved_yview)

    def test_recover_last_deleted_restores_entry_to_original_position(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        page_1 = _entry("Page 1")
        page_2 = _entry("Page 2")
        page_3 = _entry("Page 3")
        app.model = _FakeDeleteModel([page_1, page_3])
        app.deleted_entries = [[(1, page_2)]]
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
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
        page_1 = _entry("Page 1")
        page_2 = _entry("Page 2")
        page_9 = _entry("Page 9")
        app.model = _FakeDeleteModel([page_1])
        app.deleted_entries = [[(1, page_2)], [(8, page_9)]]
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: None
        app.refresh_preview = lambda: None

        app.recover_last_deleted()

        self.assertEqual(["Page 1", "Page 9"], [entry.label for entry in app.model.entries])
        self.assertEqual([[(1, "Page 2")]], [[(index, entry.label) for index, entry in group] for group in app.deleted_entries])
        self.assertEqual(1, app.page_list.selection)

    def test_quick_delete_first_records_one_undo_group(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2"), _entry("Page 3")])
        app.page_list = _FakeListbox(selection=2)
        app.status = _FakeStatus()
        app.deleted_entries = []
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("epub_layout_gui.messagebox.askyesno", return_value=True):
            app.quick_delete_first(2)

        self.assertEqual(["Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual([[(0, "Page 1"), (1, "Page 2")]], [[(index, entry.label) for index, entry in group] for group in app.deleted_entries])
        self.assertEqual(0, app.page_list.selection)
        self.assertEqual("Deleted first 2 pages.", app.status.value)

    def test_recover_last_deleted_restores_grouped_delete(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        page_1 = _entry("Page 1")
        page_2 = _entry("Page 2")
        page_3 = _entry("Page 3")
        app.model = _FakeDeleteModel([page_3])
        app.deleted_entries = [[(0, page_1), (1, page_2)]]
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        app.recover_last_deleted()

        self.assertEqual(["Page 1", "Page 2", "Page 3"], [entry.label for entry in app.model.entries])
        self.assertEqual([], app.deleted_entries)
        self.assertEqual(0, app.page_list.selection)
        self.assertEqual("Recovered 2 pages.", app.status.value)

    def test_set_selected_as_cover_updates_model_and_status(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1"), _entry("Page 2")])
        app.page_list = _FakeListbox(selection=1)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)

        app.set_selected_as_cover()

        self.assertEqual(2, app.model.cover_source_index)
        self.assertTrue(app.preserved_yview)
        self.assertEqual("Set Page 2 as cover.", app.status.value)

    def test_selected_indexes_support_multi_selection(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.page_list = _FakeListbox(selection=None)
        app.page_list.curselection = lambda: (0, 2)

        self.assertEqual([0, 2], app.selected_indexes())

    def test_insert_image_after_selected_page_calls_model(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.model = _FakeDeleteModel([_entry("Page 1")])
        app.page_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()
        app.refresh_list = lambda preserve_yview=False: setattr(app, "preserved_yview", preserve_yview)
        app.refresh_preview = lambda: setattr(app, "preview_refreshed", True)

        with patch("epub_layout_gui.filedialog.askopenfilename", return_value="/tmp/extra.png"):
            app.insert_image(before=False)

        self.assertEqual(["Page 1", "Image 2"], [entry.label for entry in app.model.entries])
        self.assertTrue(app.preserved_yview)
        self.assertEqual("Inserted image: extra.png", app.status.value)

    def test_batch_add_pdfs_updates_queue_list(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.batch_project = _FakeBatchProject()
        app.batch_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()

        with patch("epub_layout_gui.filedialog.askopenfilenames", return_value=["/tmp/a.pdf", "/tmp/b.pdf"]):
            app.add_batch_pdfs()

        self.assertEqual(["Pending a.pdf", "Pending b.pdf"], app.batch_list.items)
        self.assertEqual("Added 2 PDFs to batch.", app.status.value)

    def test_batch_validate_uses_selected_output_dir(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.batch_project = _FakeBatchProject()
        app.batch_project.add_pdf(Path("/tmp/a.pdf"))
        app.batch_list = _FakeListbox(selection=0)
        app.status = _FakeStatus()

        with patch("epub_layout_gui.filedialog.askdirectory", return_value="/tmp/out"):
            app.validate_batch()

        self.assertEqual(Path("/tmp/out"), app.batch_project.validated_dir)
        self.assertEqual(["Ready a.pdf"], app.batch_list.items)


if __name__ == "__main__":
    unittest.main()
