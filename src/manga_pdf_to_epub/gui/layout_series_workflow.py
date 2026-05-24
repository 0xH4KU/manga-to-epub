from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..epub.naming import safe_filename
from ..models.series import SeriesProject


@dataclass(frozen=True)
class SeriesExportPreflight:
    summary: dict[str, int]
    warning_lines: list[str]
    existing_output_lines: list[str]

    @property
    def message_lines(self) -> list[str]:
        return [*self.warning_lines, *self.existing_output_lines]


def series_export_preflight(project: SeriesProject, output_dir: Path, warning_limit: int = 20) -> SeriesExportPreflight:
    summary = project.validate_ready(output_dir)
    warning_lines = [
        f"Vol.{volume.volume_number:02d}: {warning}"
        for volume in project.volumes
        for warning in volume.warnings
    ]
    existing_output_lines = [
        f"Vol.{volume.volume_number:02d}: output exists and will not be overwritten: {output_path.name}"
        for volume in project.volumes
        if volume.status == "Ready"
        for output_path in [output_dir / f"{safe_filename(_generated_title(project, volume))}.epub"]
        if output_path.exists()
    ]
    return SeriesExportPreflight(summary, warning_lines[:warning_limit], existing_output_lines[:warning_limit])


def _generated_title(project: SeriesProject, volume) -> str:
    if hasattr(project, "generated_title"):
        return project.generated_title(volume)
    return f"Vol.{volume.volume_number:02d}"
