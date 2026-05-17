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
        deleted = set(self.template.deleted_source_pages)
        model.entries = [entry for entry in model.entries if entry.source_index not in deleted]
        model._blank_counter = 0
        for position in self.template.blank_positions:
            index = min(max(position, 0), len(model.entries))
            model.insert_blank(index)
        model.title = item.title or item.pdf_path.stem
        model.author = item.author or self.template.author
        model.language = self.template.language
        if self.template.cover_source_index is not None:
            try:
                model.set_cover(self.template.cover_source_index)
            except ValueError:
                model.cover_source_index = model._first_image_source_index()
        return model
