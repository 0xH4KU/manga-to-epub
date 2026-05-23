from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiagnosisCommand:
    argv: tuple[str, ...]
    cwd: Path
    output_dir: Path


@dataclass(frozen=True)
class DiagnosisRunResult:
    output_dir: Path
    stdout: str
    stderr: str


def default_diagnosis_output_dir(project_root: Path, pdf_path: Path, kind: str) -> Path:
    return Path(project_root) / "epub_layout_gui_exports" / "diagnostics" / Path(pdf_path).stem / kind


def resolve_spread_scan_command(project_root: Path, pdf_path: Path, output_dir: Path) -> DiagnosisCommand | None:
    spread_root = Path(project_root).absolute().parent / "manga-spread-continuity"
    python_path = spread_root / ".venv" / "bin" / "python"
    script_path = spread_root / "tools" / "scan_pdf_adjacent.py"
    if not python_path.exists() or not script_path.exists():
        return None
    return DiagnosisCommand(
        (
            str(python_path),
            str(script_path),
            str(pdf_path),
            "--output",
            str(output_dir),
            "--reading",
            "rtl",
            "--spread-threshold",
            "0.53",
            "--debug-limit",
            "80",
        ),
        spread_root,
        Path(output_dir),
    )


def resolve_insert_score_command(project_root: Path, pdf_path: Path, output_dir: Path) -> DiagnosisCommand | None:
    insert_root = Path(project_root).absolute().parent / "manga-insert-point-scorer"
    python_path = insert_root / ".venv" / "bin" / "python"
    package_cli = insert_root / "src" / "manga_insert_point_scorer" / "cli.py"
    if not python_path.exists() or not package_cli.exists():
        return None
    return DiagnosisCommand(
        (
            str(python_path),
            str(package_cli),
            str(pdf_path),
            "--output",
            str(output_dir),
        ),
        insert_root,
        Path(output_dir),
    )


def run_diagnosis_command(command: DiagnosisCommand) -> DiagnosisRunResult:
    command.output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        command.argv,
        cwd=command.cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return DiagnosisRunResult(command.output_dir, completed.stdout, completed.stderr)
