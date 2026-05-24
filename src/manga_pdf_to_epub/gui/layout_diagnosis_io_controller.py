from __future__ import annotations

import shutil
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .layout_diagnosis import (
    DiagnosisSession,
    InsertCandidate,
    SpreadCandidate,
    read_insert_candidates_csv,
    read_spread_candidates_csv,
)
from .layout_diagnosis_runner import (
    DiagnosisSettings,
    default_diagnosis_output_dir,
    resolve_insert_score_command,
    resolve_spread_scan_command,
    run_diagnosis_command,
)


class EpubLayoutDiagnosisIOMixin:
    def run_spread_diagnosis(self) -> None:
        if getattr(self, "model", None) is None or getattr(self, "pdf_path", None) is None:
            return
        if Path(self.pdf_path).suffix.lower() != ".pdf":
            self.status.set("Cross-page scan is available for PDF sources only.")
            return
        project_root = Path(__file__).resolve().parents[2]
        output_dir = default_diagnosis_output_dir(project_root, self.pdf_path, "spread")
        settings = getattr(self, "diagnosis_settings", DiagnosisSettings())
        command = resolve_spread_scan_command(project_root, self.pdf_path, output_dir, settings)
        if command is None:
            messagebox.showerror(
                "Spread scan unavailable",
                "Could not find sibling manga-spread-continuity environment. "
                "Use Add Selected As Spread in the Diagnose window for manual review.",
            )
            return
        self._run_background(
            "Running cross-page scan. This can take a few minutes.",
            lambda: _run_spread_scan_work(command, self.diagnosis_session.source_page_count),
            self._spread_scan_done,
            on_failure=self._spread_scan_failed,
        )

    def _spread_scan_done(self, candidates: list[SpreadCandidate]) -> None:
        self._load_spread_candidates(candidates)

    def _spread_scan_failed(self, exc: Exception) -> None:
        self.status.set("Cross-page scan failed.")
        messagebox.showerror("Cross-page scan failed", str(exc))

    def import_insert_scores(self) -> None:
        path = filedialog.askopenfilename(
            title="Import insert scores",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            self._load_insert_candidates(read_insert_candidates_csv(Path(path)))
        except ValueError as exc:
            messagebox.showerror("Import Insert Scores", str(exc))

    def run_insert_point_scoring(self) -> None:
        if getattr(self, "model", None) is None or getattr(self, "pdf_path", None) is None:
            return
        if Path(self.pdf_path).suffix.lower() != ".pdf":
            self.status.set("Insert-point scoring is available for PDF sources only.")
            return
        project_root = Path(__file__).resolve().parents[2]
        output_dir = default_diagnosis_output_dir(project_root, self.pdf_path, "insert")
        settings = getattr(self, "diagnosis_settings", DiagnosisSettings())
        command = resolve_insert_score_command(project_root, self.pdf_path, output_dir, settings)
        if command is None:
            messagebox.showerror(
                "Insert scoring unavailable",
                "Could not find sibling manga-insert-point-scorer environment. Use Import Insert Scores instead.",
            )
            return
        self._run_background(
            "Running insert-point scoring. This can take a few minutes.",
            lambda: _run_insert_scoring_work(command),
            self._insert_scoring_done,
            on_failure=self._insert_scoring_failed,
        )

    def _insert_scoring_done(self, candidates: list[InsertCandidate]) -> None:
        self._load_insert_candidates(candidates)

    def _insert_scoring_failed(self, exc: Exception) -> None:
        self.status.set("Insert-point scoring failed.")
        messagebox.showerror("Insert-point scoring failed", str(exc))

    def clear_current_diagnostics_output(self) -> None:
        pdf_path = getattr(self, "pdf_path", None)
        if pdf_path is None:
            self.status.set("Open a PDF before clearing diagnostics output.")
            return
        project_root = Path(__file__).resolve().parents[2]
        output_root = diagnosis_output_root_for_current_pdf(project_root, pdf_path)
        if not output_root.exists():
            self.status.set(f"No diagnostics output to clear for {Path(pdf_path).stem}.")
            return
        shutil.rmtree(output_root)
        self.status.set(f"Cleared diagnostics output for {Path(pdf_path).stem}.")

    def import_spread_candidates(self) -> None:
        path = filedialog.askopenfilename(
            title="Import spread candidates",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            self._load_spread_candidates(read_spread_candidates_csv(Path(path)))
        except ValueError as exc:
            messagebox.showerror("Import Spread Candidates", str(exc))

    def add_missing_spread(self) -> None:
        start_page = simpledialog.askinteger("Add Missing Spread", "Start source page:")
        if start_page is None:
            return
        end_page = simpledialog.askinteger("Add Missing Spread", "End source page:")
        if end_page is None:
            return
        try:
            self._add_missing_spread_pair(start_page, end_page)
        except ValueError as exc:
            messagebox.showerror("Add Missing Spread", str(exc))


def diagnosis_output_root_for_current_pdf(project_root: Path, pdf_path: Path) -> Path:
    return default_diagnosis_output_dir(project_root, pdf_path, "spread").parent


def _run_spread_scan_work(command, source_page_count: int = 0) -> list[SpreadCandidate]:
    result = run_diagnosis_command(command)
    candidates = read_spread_candidates_csv(result.output_dir / "adjacent_clusters.csv")
    DiagnosisSession(source_page_count).load_spread_candidates(candidates)
    return candidates


def _run_insert_scoring_work(command) -> list[InsertCandidate]:
    result = run_diagnosis_command(command)
    return read_insert_candidates_csv(result.output_dir / "gaps.csv")
