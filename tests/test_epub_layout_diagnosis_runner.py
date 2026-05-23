import tempfile
import unittest
from pathlib import Path

from manga_pdf_to_epub.epub_layout_diagnosis_runner import (
    DiagnosisCommand,
    default_diagnosis_output_dir,
    resolve_insert_score_command,
    resolve_spread_scan_command,
)


class DiagnosisRunnerTests(unittest.TestCase):
    def test_default_output_dir_is_inside_gui_exports(self):
        root = Path("/repo/manga-pdf-to-epub")
        pdf = Path("/books/Vol 01.pdf")

        self.assertEqual(
            root / "epub_layout_gui_exports" / "diagnostics" / "Vol 01" / "spread",
            default_diagnosis_output_dir(root, pdf, "spread"),
        )

    def test_resolves_sibling_spread_continuity_command_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            manga_root = Path(tmp)
            main_root = manga_root / "manga-pdf-to-epub"
            spread_root = manga_root / "manga-spread-continuity"
            python_path = spread_root / ".venv" / "bin" / "python"
            script_path = spread_root / "tools" / "scan_pdf_adjacent.py"
            python_path.parent.mkdir(parents=True)
            script_path.parent.mkdir(parents=True)
            python_path.write_text("", encoding="utf-8")
            script_path.write_text("", encoding="utf-8")
            output_dir = main_root / "out"

            command = resolve_spread_scan_command(main_root, Path("/books/book.pdf"), output_dir)

        self.assertIsInstance(command, DiagnosisCommand)
        self.assertEqual(spread_root, command.cwd)
        self.assertIn("scan_pdf_adjacent.py", command.argv[1])
        self.assertIn("--reading", command.argv)

    def test_missing_sibling_spread_command_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = resolve_spread_scan_command(Path(tmp) / "manga-pdf-to-epub", Path("/books/book.pdf"), Path(tmp) / "out")

        self.assertIsNone(command)

    def test_resolves_sibling_insert_point_command_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            manga_root = Path(tmp)
            main_root = manga_root / "manga-pdf-to-epub"
            insert_root = manga_root / "manga-insert-point-scorer"
            python_path = insert_root / ".venv" / "bin" / "python"
            package_dir = insert_root / "src" / "manga_insert_point_scorer"
            python_path.parent.mkdir(parents=True)
            package_dir.mkdir(parents=True)
            python_path.write_text("", encoding="utf-8")
            (package_dir / "cli.py").write_text("", encoding="utf-8")
            output_dir = main_root / "out"

            command = resolve_insert_score_command(main_root, Path("/books/book.pdf"), output_dir)

        self.assertIsInstance(command, DiagnosisCommand)
        self.assertEqual(insert_root, command.cwd)
        self.assertEqual(str(package_dir / "cli.py"), command.argv[1])
        self.assertIn(str(Path("/books/book.pdf")), command.argv)
        self.assertIn("--output", command.argv)
        self.assertIn(str(output_dir), command.argv)


if __name__ == "__main__":
    unittest.main()
