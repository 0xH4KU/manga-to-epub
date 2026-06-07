from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiagnosisSettings:
    spread_workers: int = 2
    spread_threshold: float = 0.53
    spread_debug_limit: int = 20
    spread_max_height: int = 900
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
    return DiagnosisCommand(
        (
            sys.executable,
            "-m",
            "manga_pdf_to_epub.diagnosis.spread_continuity.scan_pdf_adjacent",
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
        Path(project_root),
        Path(output_dir),
        {"PYTHONPATH": _builtin_scanner_pythonpath(Path(project_root))},
    )


def _builtin_scanner_pythonpath(project_root: Path) -> str:
    src_dir = project_root / "src"
    if (project_root / "manga_pdf_to_epub").exists():
        candidates = [str(project_root)]
    else:
        candidates = [str(src_dir), str(project_root)]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        candidates.append(existing)
    return os.pathsep.join(candidates)


def resolve_insert_score_command(
    project_root: Path,
    pdf_path: Path,
    output_dir: Path,
    settings: DiagnosisSettings | None = None,
) -> DiagnosisCommand | None:
    settings = settings or DiagnosisSettings()
    return DiagnosisCommand(
        (
            sys.executable,
            "-m",
            "manga_pdf_to_epub.diagnosis.insert_point_scorer.cli",
            str(pdf_path),
            "--output",
            str(output_dir),
            "--thumb-height",
            str(settings.insert_thumb_height),
        ),
        Path(project_root),
        Path(output_dir),
        {"PYTHONPATH": _builtin_scanner_pythonpath(Path(project_root))},
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
