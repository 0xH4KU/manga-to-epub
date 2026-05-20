from __future__ import annotations

import os
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
    layout_payload: dict | None = None


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
            if volume.layout_payload is not None:
                volume.layout_model.apply_preset_payload(volume.layout_payload)
                volume.layout_payload = None
        volume.layout_model.title = self.generated_title(volume)
        volume.layout_model.author = self.author
        volume.layout_model.language = self.language
        return volume.layout_model

    def mark_ready(self, volume: SeriesVolume) -> None:
        volume.status = "Ready"
        volume.error = None

    def volumes_for_scope(self, scope: str) -> list[SeriesVolume]:
        scope = scope.strip().casefold()
        if scope == "all":
            return list(self.volumes)
        if not scope:
            return []
        requested_numbers: set[int] = set()
        for token in scope.split(","):
            token = token.strip()
            if not token:
                continue
            if "-" in token:
                start_text, end_text = (part.strip() for part in token.split("-", 1))
                if not start_text.isdigit() or not end_text.isdigit():
                    raise ValueError(f"Invalid volume scope: {token}")
                start = int(start_text)
                end = int(end_text)
                if start > end:
                    raise ValueError(f"Invalid volume scope: {token}")
                requested_numbers.update(range(start, end + 1))
                continue
            if not token.isdigit():
                raise ValueError(f"Invalid volume scope: {token}")
            requested_numbers.add(int(token))
        return [volume for volume in self.volumes if volume.volume_number in requested_numbers]

    def export_ready(self, output_dir: Path) -> dict[str, int]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        validation = self.validate_ready(output_dir)
        summary = {"exported": 0, "failed": validation["failed"], "skipped": 0, "warnings": validation["warnings"]}
        for volume in self.volumes:
            if volume.status != "Ready":
                if volume.status != "Failed":
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

    def validate_ready(self, output_dir: Path) -> dict[str, int]:
        return self._validate(output_dir, ready_only=True)

    def validate_all(self, output_dir: Path) -> dict[str, int]:
        return self._validate(output_dir, ready_only=False)

    def _validate(self, output_dir: Path, ready_only: bool) -> dict[str, int]:
        output_dir = Path(output_dir)
        volume_number_counts: dict[int, int] = {}
        output_name_counts: dict[str, int] = {}
        for volume in self.volumes:
            if ready_only and volume.status != "Ready":
                continue
            volume_number_counts[volume.volume_number] = volume_number_counts.get(volume.volume_number, 0) + 1
            output_name = f"{_safe_filename(self.generated_title(volume))}.epub"
            output_name_counts[output_name] = output_name_counts.get(output_name, 0) + 1

        summary = {"ready": 0, "failed": 0, "warnings": 0}
        for volume in self.volumes:
            if ready_only and volume.status != "Ready":
                continue
            volume.warnings.clear()
            volume.error = None
            volume.output_path = output_dir / f"{_safe_filename(self.generated_title(volume))}.epub"
            output_name = volume.output_path.name
            if output_name_counts.get(output_name, 0) > 1:
                volume.warnings.append(f"Output filename collision: {output_name}")
            if volume_number_counts.get(volume.volume_number, 0) > 1:
                volume.warnings.append(f"Duplicate volume number: {volume.volume_number}")
            if not volume.pdf_path.exists():
                volume.status = "Failed"
                volume.error = f"Source PDF not found: {volume.pdf_path}"
                summary["failed"] += 1
            else:
                summary["ready"] += 1
            if volume.warnings:
                summary["warnings"] += 1
        return summary

    def to_payload(self, project_path: Path | None = None) -> dict:
        return {
            "version": 1,
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "volumes": [
                {
                    "pdf_path": _serialize_path(volume.pdf_path, project_path),
                    "volume_number": volume.volume_number,
                    "status": volume.status,
                    "output_path": _serialize_optional_path(volume.output_path, project_path),
                    "warnings": list(volume.warnings),
                    "error": volume.error,
                    "layout": _layout_payload_for_volume(volume),
                }
                for volume in self.volumes
            ],
        }

    @classmethod
    def from_payload(cls, payload: dict, project_path: Path | None = None) -> "SeriesProject":
        if payload.get("version") != 1:
            raise ValueError("Unsupported series project version")
        volumes = []
        for item in payload.get("volumes", []):
            volumes.append(
                SeriesVolume(
                    pdf_path=_deserialize_path(item.get("pdf_path", ""), project_path),
                    volume_number=int(item.get("volume_number", len(volumes) + 1)),
                    status=item.get("status") or "Unreviewed",
                    output_path=_deserialize_optional_path(item.get("output_path"), project_path),
                    warnings=list(item.get("warnings", [])),
                    error=item.get("error"),
                    layout_payload=item.get("layout"),
                )
            )
        return cls(
            payload.get("title") or "Untitled Series",
            author=payload.get("author") or "",
            language=payload.get("language") or "zh-Hant",
            volumes=volumes,
        )


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


def _layout_payload_for_volume(volume: SeriesVolume) -> dict | None:
    if volume.layout_model is not None:
        return volume.layout_model.to_preset_payload()
    return volume.layout_payload


def _serialize_optional_path(path: Path | None, project_path: Path | None) -> str | None:
    if path is None:
        return None
    return _serialize_path(path, project_path)


def _serialize_path(path: Path, project_path: Path | None) -> str:
    path = Path(path)
    if project_path is None:
        return str(path)
    try:
        return os.path.relpath(path.resolve(), Path(project_path).resolve().parent)
    except Exception:
        return str(path)


def _deserialize_optional_path(path_text: str | None, project_path: Path | None) -> Path | None:
    if path_text in (None, ""):
        return None
    return _deserialize_path(path_text, project_path)


def _deserialize_path(path_text: str, project_path: Path | None) -> Path:
    path = Path(path_text)
    if path.is_absolute() or project_path is None:
        return Path(os.path.normpath(path))
    return Path(os.path.normpath(Path(project_path).parent / path))
