import sys
import tempfile
import unittest
from pathlib import Path

from manga_pdf_to_epub.gui.layout_diagnosis_runner import (
    DiagnosisCommand,
    DiagnosisSettings,
    default_diagnosis_output_dir,
    resolve_insert_score_command,
    resolve_spread_scan_command,
    run_diagnosis_command,
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
        self.assertIn("--workers", command.argv)
        self.assertEqual("4", command.argv[command.argv.index("--workers") + 1])

    def test_spread_command_uses_manual_diagnosis_settings(self):
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
            settings = DiagnosisSettings(
                spread_workers=6,
                spread_threshold=0.61,
                spread_debug_limit=12,
                spread_max_height=1400,
                insert_thumb_height=800,
            )

            command = resolve_spread_scan_command(main_root, Path("/books/book.pdf"), main_root / "out", settings)

        self.assertEqual("6", command.argv[command.argv.index("--workers") + 1])
        self.assertEqual("0.61", command.argv[command.argv.index("--spread-threshold") + 1])
        self.assertEqual("12", command.argv[command.argv.index("--debug-limit") + 1])
        self.assertEqual("1400", command.argv[command.argv.index("--max-height") + 1])

    def test_diagnosis_settings_reject_invalid_values(self):
        with self.assertRaises(ValueError):
            DiagnosisSettings(spread_workers=0)
        with self.assertRaises(ValueError):
            DiagnosisSettings(spread_threshold=1.1)
        with self.assertRaises(ValueError):
            DiagnosisSettings(spread_debug_limit=-1)

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

            command = resolve_insert_score_command(
                main_root,
                Path("/books/book.pdf"),
                output_dir,
                DiagnosisSettings(insert_thumb_height=720),
            )

        self.assertIsInstance(command, DiagnosisCommand)
        self.assertEqual(insert_root, command.cwd)
        self.assertEqual("-m", command.argv[1])
        self.assertIn("manga_insert_point_scorer.cli", command.argv)
        self.assertIn(str(Path("/books/book.pdf")), command.argv)
        self.assertIn("--output", command.argv)
        self.assertIn(str(output_dir), command.argv)
        self.assertIn("--thumb-height", command.argv)
        self.assertEqual("720", command.argv[command.argv.index("--thumb-height") + 1])
        self.assertIsNotNone(command.env)
        self.assertEqual(str(insert_root / "src"), command.env["PYTHONPATH"])

    def test_run_diagnosis_command_passes_environment_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            script_path = tmp_path / "print_env.py"
            script_path.write_text(
                "import os\nprint(os.environ.get('DIAG_TEST_ENV'))\n",
                encoding="utf-8",
            )

            result = run_diagnosis_command(
                DiagnosisCommand(
                    (sys.executable, str(script_path)),
                    cwd=tmp_path,
                    output_dir=tmp_path / "out",
                    env={"DIAG_TEST_ENV": "ok"},
                )
            )

        self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
