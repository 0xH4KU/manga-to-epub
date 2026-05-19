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
        inferred_title, inferred_author = _infer_series_metadata(sorted_paths)
        volumes = [
            SeriesVolume(pdf_path=path, volume_number=_volume_number(path, index))
            for index, path in enumerate(sorted_paths, start=1)
        ]
        return cls(title or inferred_title, author=author or inferred_author, language=language or "zh-Hant", volumes=volumes)

    def generated_title(self, volume: SeriesVolume) -> str:
        return f"{self.title} Vol.{volume.volume_number:02d}"

    def model_for_volume(self, volume: SeriesVolume) -> LayoutModel:
        if volume.layout_model is None:
            volume.layout_model = LayoutModel.from_pdf(volume.pdf_path)
        volume.layout_model.title = self.generated_title(volume)
        volume.layout_model.author = self.author
        volume.layout_model.language = self.language
        return volume.layout_model

    def mark_ready(self, volume: SeriesVolume) -> None:
        volume.status = "Ready"
        volume.error = None

    def export_ready(self, output_dir: Path) -> dict[str, int]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = {"exported": 0, "failed": 0, "skipped": 0}
        for volume in self.volumes:
            if volume.status != "Ready":
                summary["skipped"] += 1
                continue
            try:
                model = self.model_for_volume(volume)
                volume.output_path = output_dir / f"{_safe_filename(self.generated_title(volume))}.epub"
                model.export_epub(volume.output_path, overwrite=True)
                volume.status = "Exported"
                volume.error = None
                summary["exported"] += 1
            except Exception as exc:
                volume.status = "Failed"
                volume.error = str(exc)
                summary["failed"] += 1
        return summary


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
    stem = _stem_without_volume(paths[0])
    return stem or paths[0].stem


def _infer_series_metadata(paths: list[Path]) -> tuple[str, str]:
    if not paths:
        return "Untitled Series", ""
    bracketed = re.match(r"^\s*\[([^\]]+)\]\s*\[([^\]]+)\]", paths[0].stem)
    if bracketed:
        return bracketed.group(1).strip(), bracketed.group(2).strip()
    stem = _stem_without_volume(paths[0])
    title_author = stem.rsplit(None, 1)
    if len(title_author) == 2 and _looks_like_split_title(title_author[0]):
        return title_author[0].strip(), title_author[1].strip()
    return _fallback_series_title(paths), ""


def _stem_without_volume(path: Path) -> str:
    stem = re.sub(r"\b(?:vol(?:ume)?\.?\s*)\d+\b", "", path.stem, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", stem).strip()


def _looks_like_split_title(title: str) -> bool:
    return any(separator in title for separator in (",", "，", "、", "：", ":"))


def _safe_filename(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Untitled"
