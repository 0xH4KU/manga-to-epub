import unittest
from unittest.mock import patch

from manga_pdf_to_epub.gui.layout_app import EpubLayoutApp

from tests.gui_helpers import FakeRoot, FakeStatus, FakeWidget


class EpubLayoutGuiWorkbenchTests(unittest.TestCase):
    def test_configure_window_sets_workbench_geometry_and_minimum_size(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()

        app._configure_window()

        self.assertEqual("EPUB Layout Lab", app.root.title_value)
        self.assertEqual("1280x760", app.root.geometry_value)
        self.assertEqual((1100, 680), app.root.minsize_value)

    def test_statusbar_creates_hidden_background_progress_indicator(self):
        app = EpubLayoutApp.__new__(EpubLayoutApp)
        app.root = FakeRoot()
        app.status = FakeStatus()
        app.workspace_status = FakeStatus()
        app.refresh_workspace_status = lambda: setattr(app, "workspace_refreshed", True)
        progressbars = []

        class FakeFrame(FakeWidget):
            pass

        class FakeLabel(FakeWidget):
            pass

        class FakeProgressbar(FakeWidget):
            def __init__(self, *_args, **kwargs):
                super().__init__()
                self.options = kwargs
                progressbars.append(self)

        with patch("manga_pdf_to_epub.gui.layout_workbench.ttk.Frame", FakeFrame), \
            patch("manga_pdf_to_epub.gui.layout_workbench.ttk.Label", FakeLabel), \
            patch("manga_pdf_to_epub.gui.layout_workbench.ttk.Progressbar", FakeProgressbar):
            app._build_statusbar()

        self.assertEqual([app.background_progress], progressbars)
        self.assertEqual("indeterminate", app.background_progress.options["mode"])
        self.assertEqual(140, app.background_progress.options["length"])
        self.assertFalse(app.background_progress.packed)
        self.assertTrue(app.workspace_refreshed)
