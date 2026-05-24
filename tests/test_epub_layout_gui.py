import unittest
from unittest.mock import patch
from types import SimpleNamespace

from manga_pdf_to_epub.gui.layout_app import EpubLayoutApp

from tests.gui_helpers import (
    FakeBool,
    FakeListbox,
    FakeRoot,
    FakeStatus,
    FakeWidget,
)


class EpubLayoutGuiUiTests(unittest.TestCase):
    def test_configure_window_sets_workbench_geometry_and_minimum_size(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()

        app._configure_window()

        self.assertEqual("EPUB Layout Lab", app.root.title_value)
        self.assertEqual("1280x760", app.root.geometry_value)
        self.assertEqual((1100, 680), app.root.minsize_value)

    def test_inspector_tabs_group_workbench_controls(self):
        self.assertEqual(("Edit", "Diagnose", "Book", "Series"), EpubLayoutApp._inspector_tab_titles())

    def test_edit_inspector_sections_follow_layout_workflow(self):
        self.assertEqual(("Insert", "Delete", "Repair"), EpubLayoutApp._edit_section_titles())

    def test_series_inspector_sections_follow_series_workflow(self):
        self.assertEqual(("Review", "Export"), EpubLayoutApp._series_section_titles())

    def test_metadata_labels_switch_between_single_pdf_and_series_modes(self):
        self.assertEqual(("Title", "Author"), EpubLayoutApp._metadata_label_texts(series_mode=False))
        self.assertEqual(("Series Title", "Series Author"), EpubLayoutApp._metadata_label_texts(series_mode=True))

    def test_inspector_tab_state_switches_active_tab(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.inspector_tabs = {
            "Edit": SimpleNamespace(raise_count=0, tkraise=lambda: None),
            "Series": SimpleNamespace(raise_count=0, tkraise=lambda: None),
        }
        app.inspector_tab_buttons = {}

        app._show_inspector_tab("Series")

        self.assertEqual("Series", app.active_inspector_tab)

    def test_preview_checkbox_label_is_explicitly_preview_only(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.apple_preview = FakeBool(True)
        app.title_var = SimpleNamespace()
        app.author_var = SimpleNamespace()
        app.language_var = SimpleNamespace()
        app.exclude_cover_var = FakeBool(False)
        app.inspector_tabs = {}
        app.inspector_tab_buttons = {}
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app.refresh_preview = lambda: None
        app.refresh_workspace_status = lambda: None
        widgets = []

        class FakeFrame(FakeWidget):
            pass

        class FakePanedwindow(FakeWidget):
            pass

        class FakeButton(FakeWidget):
            def __init__(self, *_args, **kwargs):
                super().__init__()
                self.options = kwargs

        class FakeLabel(FakeButton):
            pass

        class FakeCheckbutton(FakeButton):
            def __init__(self, *_args, **kwargs):
                super().__init__(*_args, **kwargs)
                widgets.append(self)

        class FakeListbox(FakeWidget):
            def __init__(self, *_args, **_kwargs):
                super().__init__()

            def bind(self, *_args, **_kwargs):
                pass

            def pack_propagate(self, *_args, **_kwargs):
                pass

            def yview(self, *_args, **_kwargs):
                pass

        class FakeCanvas(FakeListbox):
            def create_window(self, *_args, **_kwargs):
                return 1

            def configure(self, **kwargs):
                self.options.update(kwargs)

            def itemconfigure(self, *_args, **_kwargs):
                pass

            def bbox(self, *_args, **_kwargs):
                return (0, 0, 1, 1)

        with patch("manga_pdf_to_epub.gui.layout_app.ttk.Frame", FakeFrame), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Panedwindow", FakePanedwindow), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Label", FakeLabel), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Checkbutton", FakeCheckbutton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Scrollbar", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Separator", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Entry", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Listbox", FakeListbox), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Canvas", FakeCanvas):
            app._build_ui()

        labels = [widget.options.get("text") for widget in widgets]
        self.assertIn("Preview Apple Books cover gap", labels)
        self.assertNotIn("Apple Books-like cover-right gap", labels)
        preview_toggle = next(widget for widget in widgets if widget.options.get("text") == "Preview Apple Books cover gap")
        self.assertEqual(app.refresh_preview_after_diagnosis_layout_option_change, preview_toggle.options.get("command"))

    def test_diagnose_inspector_uses_window_entry_point(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.apple_preview = FakeBool(True)
        app.title_var = SimpleNamespace()
        app.author_var = SimpleNamespace()
        app.language_var = SimpleNamespace()
        app.exclude_cover_var = FakeBool(False)
        app.inspector_tabs = {}
        app.inspector_tab_buttons = {}
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app.refresh_preview = lambda: None
        app.refresh_workspace_status = lambda: None
        app.open_diagnose_window = lambda: setattr(app, "diagnose_opened", True)
        buttons = []
        class FakeFrame(FakeWidget):
            pass
        class FakePanedwindow(FakeWidget):
            pass

        class FakeButton(FakeWidget):
            def __init__(self, *_args, **kwargs):
                super().__init__()
                self.options = kwargs
                buttons.append(self)

        class FakeLabel(FakeButton):
            pass

        class FakeCheckbutton(FakeButton):
            pass

        class FakeListbox(FakeWidget):
            def bind(self, *_args, **_kwargs):
                pass

            def yview(self, *_args, **_kwargs):
                pass

        class FakeCanvas(FakeListbox):
            def configure(self, **kwargs):
                self.options.update(kwargs)

            def create_window(self, *_args, **_kwargs):
                return 1

            def itemconfigure(self, *_args, **_kwargs):
                pass

            def bbox(self, *_args, **_kwargs):
                return (0, 0, 1, 1)

        with patch("manga_pdf_to_epub.gui.layout_app.ttk.Frame", FakeFrame), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Panedwindow", FakePanedwindow), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Label", FakeLabel), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Checkbutton", FakeCheckbutton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Scrollbar", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Separator", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Entry", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Listbox", FakeListbox), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Canvas", FakeCanvas):
            app._build_ui()

        button_by_label = {button.options.get("text"): button for button in buttons}
        self.assertIn("Open Diagnose Window", button_by_label)
        self.assertTrue({"Import Spread Candidates...", "Run Cross-Page Scan"}.isdisjoint(button_by_label))
        self.assertTrue(button_by_label["Open Diagnose Window"].options["command"]() is None and app.diagnose_opened)

    def test_series_tab_omits_old_batch_template_workflow(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.apple_preview = FakeBool(True)
        app.title_var = SimpleNamespace()
        app.author_var = SimpleNamespace()
        app.language_var = SimpleNamespace()
        app.exclude_cover_var = FakeBool(False)
        app.inspector_tabs = {}
        app.inspector_tab_buttons = {}
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app.refresh_preview = lambda: None
        app.refresh_workspace_status = lambda: None
        widgets = []

        class FakeFrame(FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parent = args[0] if args else None
                self.options = kwargs
                widgets.append(self)

        class FakePanedwindow(FakeFrame):
            pass

        class FakeButton(FakeFrame):
            pass

        class FakeLabel(FakeFrame):
            pass

        class FakeCheckbutton(FakeFrame):
            pass

        class FakeListbox(FakeFrame):
            def bind(self, *_args, **_kwargs):
                pass

            def yview(self, *_args, **_kwargs):
                pass

        class FakeCanvas(FakeListbox):
            def create_window(self, *_args, **_kwargs):
                return 1

            def itemconfigure(self, *_args, **_kwargs):
                pass

            def bbox(self, *_args, **_kwargs):
                return (0, 0, 1, 1)

        with patch("manga_pdf_to_epub.gui.layout_app.ttk.Frame", FakeFrame), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Panedwindow", FakePanedwindow), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Label", FakeLabel), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Checkbutton", FakeCheckbutton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Scrollbar", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Separator", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Entry", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Listbox", FakeListbox), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Canvas", FakeCanvas):
            app._build_ui()

        labels = [widget.options.get("text") for widget in widgets]
        self.assertNotIn("Batch queue", labels)
        self.assertNotIn("Use Current Layout As Template", labels)
        self.assertNotIn("Load Template Preset...", labels)
        self.assertNotIn("Validate Batch...", labels)
        self.assertNotIn("Export Ready...", labels)
        self.assertNotIn("Export All...", labels)
        self.assertIn("Mark Selected Volume Ready", labels)
        self.assertIn("Unready Selected", labels)
        self.assertIn("Export Ready Series...", labels)
        self.assertNotIn("Delete First...", labels)
        self.assertNotIn("Delete Last...", labels)
        self.assertNotIn("Delete Range...", labels)

    def test_toolbar_buttons_use_even_left_to_right_spacing(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.apple_preview = FakeBool(True)
        app.title_var = SimpleNamespace()
        app.author_var = SimpleNamespace()
        app.language_var = SimpleNamespace()
        app.exclude_cover_var = FakeBool(False)
        app.inspector_tabs = {}
        app.inspector_tab_buttons = {}
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app.refresh_preview = lambda: None
        app.refresh_workspace_status = lambda: None
        frames = []
        buttons = []

        class FakeFrame(FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parent = args[0] if args else None
                self.options = kwargs
                frames.append(self)

        class FakePanedwindow(FakeFrame):
            pass

        class FakeButton(FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parent = args[0] if args else None
                self.options = kwargs
                buttons.append(self)

        class FakeLabel(FakeButton):
            pass

        class FakeCheckbutton(FakeButton):
            pass

        class FakeListbox(FakeWidget):
            def bind(self, *_args, **_kwargs):
                pass

            def yview(self, *_args, **_kwargs):
                pass

        class FakeCanvas(FakeListbox):
            def create_window(self, *_args, **_kwargs):
                return 1

            def configure(self, **kwargs):
                self.options.update(kwargs)

            def itemconfigure(self, *_args, **_kwargs):
                pass

            def bbox(self, *_args, **_kwargs):
                return (0, 0, 1, 1)

        with patch("manga_pdf_to_epub.gui.layout_app.ttk.Frame", FakeFrame), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Panedwindow", FakePanedwindow), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Label", FakeLabel), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Checkbutton", FakeCheckbutton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Scrollbar", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Separator", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Entry", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Listbox", FakeListbox), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Canvas", FakeCanvas):
            app._build_ui()

        toolbar = frames[0]
        toolbar_rows = [frame for frame in frames if frame.parent is toolbar]

        self.assertEqual(1, len(toolbar_rows))
        toolbar_row = toolbar_rows[0]
        self.assertEqual("center", toolbar_row.pack_args[-1][1].get("anchor"))
        toolbar_buttons = [button for button in buttons if button.parent is toolbar_row]

        self.assertEqual(
            [
                "Import Series...",
                "Open Source",
                "Export EPUB",
                "Export Ready Series...",
                "Open Project...",
                "Save Project...",
                "Save Preset",
                "Load Preset",
                "Command Palette...",
            ],
            [button.options.get("text") for button in toolbar_buttons],
        )
        for button in toolbar_buttons[:-1]:
            pack_kwargs = button.pack_args[-1][1]
            self.assertEqual("left", pack_kwargs.get("side"))
            self.assertEqual((0, 8), pack_kwargs.get("padx"))
        last_pack_kwargs = toolbar_buttons[-1].pack_args[-1][1]
        self.assertEqual("left", last_pack_kwargs.get("side"))
        self.assertEqual((0, 0), last_pack_kwargs.get("padx"))

    def test_single_pdf_navigation_hides_series_volumes_by_default(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.apple_preview = FakeBool(True)
        app.series_project = None
        app.title_var = SimpleNamespace()
        app.author_var = SimpleNamespace()
        app.language_var = SimpleNamespace()
        app.exclude_cover_var = FakeBool(False)
        app.inspector_tabs = {}
        app.inspector_tab_buttons = {}
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app.refresh_preview = lambda: None
        app.refresh_workspace_status = lambda: None
        widgets = []

        class FakeFrame(FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.options = kwargs
                widgets.append(self)

        class FakePanedwindow(FakeFrame):
            pass

        class FakeButton(FakeFrame):
            pass

        class FakeLabel(FakeFrame):
            pass

        class FakeCheckbutton(FakeFrame):
            pass

        class FakeListbox(FakeFrame):
            def bind(self, *_args, **_kwargs):
                pass

            def yview(self, *_args, **_kwargs):
                pass

        class FakeCanvas(FakeListbox):
            def create_window(self, *_args, **_kwargs):
                return 1

            def itemconfigure(self, *_args, **_kwargs):
                pass

            def bbox(self, *_args, **_kwargs):
                return (0, 0, 1, 1)

        with patch("manga_pdf_to_epub.gui.layout_app.ttk.Frame", FakeFrame), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Panedwindow", FakePanedwindow), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Label", FakeLabel), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Checkbutton", FakeCheckbutton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Scrollbar", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Separator", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Entry", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Listbox", FakeListbox), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Canvas", FakeCanvas):
            app._build_ui()

        labels = [widget.options.get("text") for widget in widgets]
        self.assertIn("Import Series...", labels)
        self.assertIsNot(app.series_list, app.page_list)
        self.assertFalse(app.series_pane.packed)
        self.assertTrue(app.spine_pane.packed)

    def test_left_navigation_places_series_volumes_beside_spine_order(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.apple_preview = FakeBool(True)
        app.series_project = SimpleNamespace(volumes=[])
        app.title_var = SimpleNamespace()
        app.author_var = SimpleNamespace()
        app.language_var = SimpleNamespace()
        app.exclude_cover_var = FakeBool(False)
        app.inspector_tabs = {}
        app.inspector_tab_buttons = {}
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app.refresh_preview = lambda: None
        app.refresh_workspace_status = lambda: None

        class FakeFrame(FakeWidget):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.parent = args[0] if args else None
                self.options = kwargs

        class FakePanedwindow(FakeFrame):
            pass

        class FakeButton(FakeFrame):
            pass

        class FakeLabel(FakeFrame):
            pass

        class FakeCheckbutton(FakeFrame):
            pass

        class FakeListbox(FakeFrame):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.options = kwargs

            def bind(self, *_args, **_kwargs):
                pass

            def yview(self, *_args, **_kwargs):
                pass

        class FakeCanvas(FakeListbox):
            def create_window(self, *_args, **_kwargs):
                return 1

            def itemconfigure(self, *_args, **_kwargs):
                pass

            def bbox(self, *_args, **_kwargs):
                return (0, 0, 1, 1)

        with patch("manga_pdf_to_epub.gui.layout_app.ttk.Frame", FakeFrame), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Panedwindow", FakePanedwindow), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Button", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Label", FakeLabel), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Checkbutton", FakeCheckbutton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Scrollbar", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Separator", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.ttk.Entry", FakeButton), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Listbox", FakeListbox), \
            patch("manga_pdf_to_epub.gui.layout_app.tk.Canvas", FakeCanvas):
            app._build_ui()

        self.assertEqual(app.series_list.parent, app.series_pane)
        self.assertEqual(app.page_list.parent, app.spine_pane)
        self.assertTrue(app.series_pane.packed)
        self.assertTrue(app.spine_pane.packed)
        self.assertIsNot(app.series_list.parent, app.page_list.parent)
        self.assertEqual("extended", app.series_list.options.get("selectmode"))

    def test_series_navigation_stacks_when_default_width_is_too_narrow(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_project = SimpleNamespace(volumes=[])
        app.series_pane = FakeWidget()
        app.spine_pane = FakeWidget()

        app._sync_navigation_mode(available_width=520)

        self.assertTrue(app.series_pane.packed)
        self.assertTrue(app.spine_pane.packed)
        self.assertEqual("top", app.series_pane.pack_args[-1][1]["side"])
        self.assertEqual("top", app.spine_pane.pack_args[-1][1]["side"])

    def test_series_navigation_uses_columns_when_width_allows(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.series_project = SimpleNamespace(volumes=[])
        app.series_pane = FakeWidget()
        app.spine_pane = FakeWidget()

        app._sync_navigation_mode(available_width=760)

        self.assertEqual("left", app.series_pane.pack_args[-1][1]["side"])
        self.assertEqual("left", app.spine_pane.pack_args[-1][1]["side"])

if __name__ == "__main__":
    unittest.main()
