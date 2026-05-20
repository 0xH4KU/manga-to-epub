import ast
import unittest
from pathlib import Path


class ProjectGuardrailTests(unittest.TestCase):
    def test_gui_module_keeps_delete_history_in_dedicated_helper(self):
        source = Path("epub_layout_gui.py").read_text(encoding="utf-8")
        self.assertIn("from epub_layout_history import CoverState, DeleteHistory", source)
        self.assertNotIn("deleted_cover_states", source)

    def test_gui_app_class_stays_below_current_complexity_ceiling(self):
        tree = ast.parse(Path("epub_layout_gui.py").read_text(encoding="utf-8"))
        app_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "EpubLayoutApp")
        self.assertLessEqual(app_class.end_lineno - app_class.lineno + 1, 1450)


if __name__ == "__main__":
    unittest.main()
