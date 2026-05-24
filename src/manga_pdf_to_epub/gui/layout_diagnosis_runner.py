from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiagnosisSettings:
    spread_workers: int = 4
    spread_threshold: float = 0.53
    spread_debug_limit: int = 80
    spread_max_height: int = 1000
    insert_thumb_height: int = 900

    def __post_init__(self) -> None:
        if self.spread_workers < 1:
            raise ValueError("Spread scan workers must be at least 1.")
        if not 0 < self.spread_threshold <= 1:
            raise ValueError("Spread threshold must be between 0 and 1.")
        if self.spread_debug_limit < 0:
            raise ValueError("Debug image limit must be 0 or greater.")
        if self.spread_max_height < 100:
            raise ValueError("Spread render height must be at least 100.")
        if self.insert_thumb_height < 100:
            raise ValueError("Insert thumbnail height must be at least 100.")


@dataclass(frozen=True)
class DiagnosisCommand:
    argv: tuple[str, ...]
    cwd: Path
    output_dir: Path
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class DiagnosisRunResult:
    output_dir: Path
    stdout: str
    stderr: str


def default_diagnosis_output_dir(project_root: Path, pdf_path: Path, kind: str) -> Path:
    return Path(project_root) / "epub_layout_gui_exports" / "diagnostics" / Path(pdf_path).stem / kind


def resolve_spread_scan_command(
    project_root: Path,
    pdf_path: Path,
    output_dir: Path,
    settings: DiagnosisSettings | None = None,
) -> DiagnosisCommand | None:
    settings = settings or DiagnosisSettings()
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
            str(settings.spread_threshold),
            "--debug-limit",
            str(settings.spread_debug_limit),
            "--workers",
            str(settings.spread_workers),
            "--max-height",
            str(settings.spread_max_height),
        ),
        spread_root,
        Path(output_dir),
    )


def resolve_insert_score_command(
    project_root: Path,
    pdf_path: Path,
    output_dir: Path,
    settings: DiagnosisSettings | None = None,
) -> DiagnosisCommand | None:
    settings = settings or DiagnosisSettings()
    insert_root = Path(project_root).absolute().parent / "manga-insert-point-scorer"
    python_path = insert_root / ".venv" / "bin" / "python"
    package_cli = insert_root / "src" / "manga_insert_point_scorer" / "cli.py"
    if not python_path.exists() or not package_cli.exists():
        return None
    return DiagnosisCommand(
        (
            str(python_path),
            "-m",
            "manga_insert_point_scorer.cli",
            str(pdf_path),
            "--output",
            str(output_dir),
            "--thumb-height",
            str(settings.insert_thumb_height),
        ),
        insert_root,
        Path(output_dir),
        {"PYTHONPATH": str(insert_root / "src")},
    )


def run_diagnosis_command(command: DiagnosisCommand) -> DiagnosisRunResult:
    command.output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ | (command.env or {})
    completed = subprocess.run(
        command.argv,
        cwd=command.cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    return DiagnosisRunResult(command.output_dir, completed.stdout, completed.stderr)
