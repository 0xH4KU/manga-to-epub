from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from epub_layout_model import LayoutModel


@dataclass
class BatchItem:
    pdf_path: Path
    page_count: int | None = None
    title: str = ""
    author: str = ""
    output_path: Path | None = None
    status: str = "Pending"
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class LayoutTemplate:
    source_page_count: int
    blank_positions: list[int]
    deleted_source_pages: list[int]
    title: str
    author: str
    language: str
    cover_source_index: int | None
    exclude_cover_from_reading: bool
    cover_entry_id: str | None = None
    entries: list[dict] = field(default_factory=list)


class BatchProject:
    def __init__(self, template: LayoutTemplate):
        self.template = template
        self.items: list[BatchItem] = []

    @classmethod
    def from_template(cls, model: LayoutModel) -> "BatchProject":
        source_order = [entry.source_index for entry in model.entries if entry.source_index is not None]
        deleted_source_pages = sorted(set(range(1, model.source_page_count + 1)) - set(source_order))
        blank_positions = [index for index, entry in enumerate(model.entries) if entry.is_blank]
        return cls(
            LayoutTemplate(
                source_page_count=model.source_page_count,
                blank_positions=blank_positions,
                deleted_source_pages=deleted_source_pages,
                title=model.title,
                author=model.author,
                language=model.language,
                cover_source_index=model.cover_source_index,
                exclude_cover_from_reading=model.exclude_cover_from_reading,
                cover_entry_id=model.cover_entry_id,
                entries=[model._preset_entry_payload(entry) for entry in model.entries],
            )
        )

    @classmethod
    def from_preset(cls, preset_path: Path) -> "BatchProject":
        model = LayoutModel(Path(preset_path), [])
        payload = model.load_preset_payload(preset_path)
        metadata = payload.get("metadata", {})
        cover = payload.get("cover", {})
        deleted_source_pages = _deleted_source_pages_from_entries(
            int(payload.get("source_page_count", 0)),
            payload.get("entries", []),
        )
        blank_positions = [
            index for index, entry in enumerate(payload.get("entries", [])) if entry.get("kind") == "blank"
        ]
        return cls(
            LayoutTemplate(
                source_page_count=int(payload.get("source_page_count", 0)),
                blank_positions=blank_positions,
                deleted_source_pages=deleted_source_pages,
                title=metadata.get("title") or Path(preset_path).stem,
                author=metadata.get("author") or "",
                language=metadata.get("language") or "zh-Hant",
                cover_source_index=cover.get("source_index") if cover.get("kind") == "source" else None,
                exclude_cover_from_reading=bool(metadata.get("exclude_cover_from_reading", False)),
                cover_entry_id=cover.get("entry_id") if cover.get("kind") == "inserted" else None,
                entries=payload.get("entries", []),
            )
        )

    def add_pdf(self, pdf_path: Path) -> BatchItem:
        item = BatchItem(pdf_path=Path(pdf_path), title=Path(pdf_path).stem)
        self.items.append(item)
        return item

    def validate_all(self, output_dir: Path) -> None:
        output_dir = Path(output_dir)
        seen_outputs: set[Path] = set()
        for item in self.items:
            item.warnings.clear()
            item.error = None
            item.output_path = output_dir / item.pdf_path.with_suffix(".epub").name
            if item.output_path in seen_outputs:
                item.warnings.append(f"Output filename collision: {item.output_path.name}")
            seen_outputs.add(item.output_path)
            try:
                model = LayoutModel.from_pdf(item.pdf_path)
                item.page_count = model.source_page_count
                if item.page_count != self.template.source_page_count:
                    item.warnings.append(
                        f"Page count differs: expected {self.template.source_page_count}, got {item.page_count}"
                    )
                item.status = "Warning" if item.warnings else "Ready"
            except Exception as exc:
                item.status = "Failed"
                item.error = str(exc)

    def export_ready(self, output_dir: Path) -> dict[str, int]:
        return self._export(output_dir, include_warnings=False)

    def export_all(self, output_dir: Path) -> dict[str, int]:
        return self._export(output_dir, include_warnings=True)

    def _export(self, output_dir: Path, include_warnings: bool) -> dict[str, int]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self.validate_all(output_dir)
        summary = {"exported": 0, "failed": 0, "skipped": 0}
        for item in self.items:
            if item.status == "Failed":
                summary["failed"] += 1
                continue
            if item.status == "Warning" and not include_warnings:
                summary["skipped"] += 1
                continue
            try:
                model = self._model_for_item(item)
                model.export_epub(item.output_path or output_dir / item.pdf_path.with_suffix(".epub").name, overwrite=True)
                item.status = "Exported"
                item.error = None
                summary["exported"] += 1
            except Exception as exc:
                item.status = "Failed"
                item.error = str(exc)
                summary["failed"] += 1
        return summary

    def _model_for_item(self, item: BatchItem) -> LayoutModel:
        model = LayoutModel.from_pdf(item.pdf_path)
        if self.template.entries:
            payload = {
                "version": 2,
                "metadata": {
                    "title": item.title or item.pdf_path.stem,
                    "author": item.author or self.template.author,
                    "language": self.template.language,
                    "exclude_cover_from_reading": self.template.exclude_cover_from_reading,
                },
                "cover": self._cover_payload(),
                "entries": self.template.entries,
            }
            model.apply_preset_payload(payload)
        else:
            deleted = set(self.template.deleted_source_pages)
            model.entries = [entry for entry in model.entries if entry.source_index not in deleted]
            model._blank_counter = 0
            for position in self.template.blank_positions:
                index = min(max(position, 0), len(model.entries))
                model.insert_blank(index)
        model.title = item.title or item.pdf_path.stem
        model.author = item.author or self.template.author
        model.language = self.template.language
        model.exclude_cover_from_reading = self.template.exclude_cover_from_reading
        if self.template.cover_entry_id is not None:
            model.cover_entry_id = self.template.cover_entry_id
            model.cover_source_index = None
            model._ensure_valid_cover()
        elif self.template.cover_source_index is not None:
            try:
                model.set_cover(self.template.cover_source_index)
            except ValueError:
                model.cover_source_index = model._first_image_source_index()
        return model

    def _cover_payload(self) -> dict:
        if self.template.cover_entry_id is not None:
            return {"kind": "inserted", "source_index": None, "entry_id": self.template.cover_entry_id}
        if self.template.cover_source_index is not None:
            return {"kind": "source", "source_index": self.template.cover_source_index, "entry_id": None}
        return {"kind": "first-image", "source_index": None, "entry_id": None}


def _deleted_source_pages_from_entries(source_page_count: int, entries: list[dict]) -> list[int]:
    source_order = {entry.get("source_index") for entry in entries if entry.get("kind") == "source"}
    return sorted(set(range(1, source_page_count + 1)) - source_order)
