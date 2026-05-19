from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from epub_layout_model import LayoutModel


@dataclass
class SeriesVolume:
    pdf_path: Path
    volume_number: int
    status: str = "Unreviewed"
    layout_model: LayoutModel | None = None
    output_path: Path | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class SeriesProject:
    title: str
    author: str = ""
    language: str = "zh-Hant"
    volumes: list[SeriesVolume] = field(default_factory=list)

    @classmethod
    def from_pdfs(
        cls,
        pdf_paths: list[Path],
        title: str | None = None,
        author: str = "",
        language: str = "zh-Hant",
    ) -> "SeriesProject":
        sorted_paths = sorted((Path(path) for path in pdf_paths), key=_natural_path_key)
        inferred_title = title or _fallback_series_title(sorted_paths)
        volumes = [
            SeriesVolume(pdf_path=path, volume_number=_volume_number(path, index))
            for index, path in enumerate(sorted_paths, start=1)
        ]
        return cls(inferred_title, author=author, language=language or "zh-Hant", volumes=volumes)

    def generated_title(self, volume: SeriesVolume) -> str:
        return f"{self.title} Vol.{volume.volume_number:02d}"

    def model_for_volume(self, volume: SeriesVolume) -> LayoutModel:
        if volume.layout_model is None:
            volume.layout_model = LayoutModel.from_pdf(volume.pdf_path)
        volume.layout_model.title = self.generated_title(volume)
        volume.layout_model.author = self.author
        volume.layout_model.language = self.language
        return volume.layout_model


def _natural_path_key(path: Path) -> list[int | str]:
    parts: list[int | str] = []
    for chunk in re.split(r"(\d+)", path.stem.casefold()):
        if chunk.isdigit():
            parts.append(int(chunk))
        elif chunk:
            parts.append(chunk)
    return parts


def _volume_number(path: Path, fallback: int) -> int:
    match = re.search(r"\b(?:vol(?:ume)?\.?\s*)(\d+)\b", path.stem, re.IGNORECASE)
    if match:
        return int(match.group(1))
    trailing = re.search(r"(\d+)\s*$", path.stem)
    if trailing:
        return int(trailing.group(1))
    return fallback


def _fallback_series_title(paths: list[Path]) -> str:
    if not paths:
        return "Untitled Series"
    stem = paths[0].stem
    stem = re.sub(r"\b(?:vol(?:ume)?\.?\s*)\d+\b", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or paths[0].stem
