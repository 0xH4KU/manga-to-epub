import sys
import tempfile
import unittest
import subprocess
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

    def test_resolves_builtin_spread_continuity_command(self):
        output_dir = Path("/repo/manga-pdf-to-epub/out")

        command = resolve_spread_scan_command(Path("/repo/manga-pdf-to-epub"), Path("/books/book.pdf"), output_dir)

        self.assertIsInstance(command, DiagnosisCommand)
        self.assertEqual(Path("/repo/manga-pdf-to-epub"), command.cwd)
        self.assertEqual(sys.executable, command.argv[0])
        self.assertEqual("-m", command.argv[1])
        self.assertEqual("manga_pdf_to_epub.diagnosis.spread_continuity.scan_pdf_adjacent", command.argv[2])
        self.assertIn("--reading", command.argv)
        self.assertIn("--workers", command.argv)
        self.assertEqual("2", command.argv[command.argv.index("--workers") + 1])
        self.assertEqual("20", command.argv[command.argv.index("--debug-limit") + 1])
        self.assertEqual("900", command.argv[command.argv.index("--max-height") + 1])
        self.assertIsNotNone(command.env)
        self.assertIn(str(Path("/repo/manga-pdf-to-epub/src")), command.env["PYTHONPATH"])

    def test_spread_command_uses_manual_diagnosis_settings(self):
        settings = DiagnosisSettings(
            spread_workers=6,
            spread_threshold=0.61,
            spread_debug_limit=12,
            spread_max_height=1400,
            insert_thumb_height=800,
        )

        command = resolve_spread_scan_command(Path("/repo/manga-pdf-to-epub"), Path("/books/book.pdf"), Path("/repo/out"), settings)

        self.assertEqual("6", command.argv[command.argv.index("--workers") + 1])
        self.assertEqual("0.61", command.argv[command.argv.index("--spread-threshold") + 1])
        self.assertEqual("12", command.argv[command.argv.index("--debug-limit") + 1])
        self.assertEqual("1400", command.argv[command.argv.index("--max-height") + 1])

    def test_builtin_spread_scanner_module_is_runnable(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "manga_pdf_to_epub.diagnosis.spread_continuity.scan_pdf_adjacent",
                "--help",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        self.assertIn("--workers", completed.stdout)
        self.assertIn("--max-height", completed.stdout)

    def test_diagnosis_settings_reject_invalid_values(self):
        with self.assertRaises(ValueError):
            DiagnosisSettings(spread_workers=0)
        with self.assertRaises(ValueError):
            DiagnosisSettings(spread_threshold=1.1)
        with self.assertRaises(ValueError):
            DiagnosisSettings(spread_debug_limit=-1)

    def test_resolves_builtin_insert_point_command(self):
        command = resolve_insert_score_command(
            Path("/repo/manga-pdf-to-epub"),
            Path("/books/book.pdf"),
            Path("/repo/manga-pdf-to-epub/out"),
            DiagnosisSettings(insert_thumb_height=720),
        )

        self.assertIsInstance(command, DiagnosisCommand)
        self.assertEqual(Path("/repo/manga-pdf-to-epub"), command.cwd)
        self.assertEqual(sys.executable, command.argv[0])
        self.assertEqual("-m", command.argv[1])
        self.assertEqual("manga_pdf_to_epub.diagnosis.insert_point_scorer.cli", command.argv[2])
        self.assertIn(str(Path("/books/book.pdf")), command.argv)
        self.assertIn("--output", command.argv)
        self.assertIn(str(Path("/repo/manga-pdf-to-epub/out")), command.argv)
        self.assertIn("--thumb-height", command.argv)
        self.assertEqual("720", command.argv[command.argv.index("--thumb-height") + 1])
        self.assertIsNotNone(command.env)
        self.assertIn(str(Path("/repo/manga-pdf-to-epub/src")), command.env["PYTHONPATH"])

    def test_builtin_insert_scorer_module_is_runnable(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "manga_pdf_to_epub.diagnosis.insert_point_scorer.cli",
                "--help",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        self.assertIn("--thumb-height", completed.stdout)

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
