import ast
import unittest
from pathlib import Path


class ProjectGuardrailTests(unittest.TestCase):
    def test_gui_module_keeps_delete_history_in_dedicated_helper(self):
        source = Path("src/manga_pdf_to_epub/epub_layout_gui.py").read_text(encoding="utf-8")
        self.assertIn("from .epub_layout_history import CoverState, DeleteHistory", source)
        self.assertNotIn("deleted_cover_states", source)

    def test_gui_app_class_stays_below_current_complexity_ceiling(self):
        tree = ast.parse(Path("src/manga_pdf_to_epub/epub_layout_gui.py").read_text(encoding="utf-8"))
        app_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "EpubLayoutApp")
        self.assertLessEqual(app_class.end_lineno - app_class.lineno + 1, 1450)

    def test_gui_behavior_tests_stay_split_by_workflow(self):
        test_files = [
            Path("tests/test_epub_layout_gui.py"),
            Path("tests/test_epub_layout_gui_commands.py"),
            Path("tests/test_epub_layout_gui_editing.py"),
            Path("tests/test_epub_layout_gui_preview.py"),
            Path("tests/test_epub_layout_gui_project.py"),
            Path("tests/test_epub_layout_gui_series.py"),
        ]

        missing = [str(path) for path in test_files if not path.exists()]
        self.assertEqual([], missing)
        for path in test_files:
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertLessEqual(len(lines), 550, str(path))

    def test_cbz_export_files_are_removed(self):
        removed_paths = [
            Path("pdf_to_cbz_lossless.py"),
            Path("src/manga_pdf_to_epub/pdf_to_cbz_lossless.py"),
            Path("tests/test_pdf_to_cbz_lossless.py"),
        ]

        self.assertEqual([], [str(path) for path in removed_paths if path.exists()])

    def test_runtime_code_does_not_import_cbz_module(self):
        references = []
        for directory in (Path("src"), Path("tests")):
            for path in directory.rglob("*.py"):
                if path == Path("tests/test_project_guardrails.py"):
                    continue
                source = path.read_text(encoding="utf-8")
                if "pdf_to_cbz_lossless" in source:
                    references.append(str(path))

        self.assertEqual([], references)


if __name__ == "__main__":
    unittest.main()
