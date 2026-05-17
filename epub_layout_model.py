from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pdf_to_cbz_lossless import ImageStream, image_to_archive_member, images_in_pdf_page_order
from pdf_to_epub_lossless import EpubPage, _media_type_for_ext, write_epub_from_pages


@dataclass(frozen=True)
class LayoutEntry:
    label: str
    page: EpubPage
    source_index: int | None = None

    @property
    def is_blank(self) -> bool:
        return self.page.is_blank


class LayoutModel:
    def __init__(self, source_path: Path, entries: list[LayoutEntry], source_page_count: int | None = None):
        self.source_path = source_path
        self.entries = entries
        self._source_page_count = source_page_count or max((entry.source_index or 0 for entry in entries), default=0)
        self._blank_counter = sum(1 for entry in entries if entry.is_blank)

    @classmethod
    def from_pdf(cls, pdf_path: Path) -> "LayoutModel":
        images = images_in_pdf_page_order(pdf_path)
        entries = [_entry_from_image(image, max(4, len(str(len(images))))) for image in images]
        return cls(pdf_path, entries, source_page_count=len(images))

    def insert_blank(self, index: int) -> None:
        if index < 0 or index > len(self.entries):
            raise IndexError("Blank insertion index out of range")
        reference = _reference_page(self.entries, index)
        self._blank_counter += 1
        blank_id = f"blank-{self._blank_counter:04d}"
        page = EpubPage(
            index=self._blank_counter,
            width=reference.width,
            height=reference.height,
            image_href=None,
            image_media_type=None,
            image_data=None,
            xhtml_href=f"xhtml/{blank_id}.xhtml",
            item_id=blank_id,
            label=f"Blank {self._blank_counter}",
            is_blank=True,
        )
        self.entries.insert(index, LayoutEntry(page.label, page))

    def delete_blank(self, index: int) -> None:
        if index < 0 or index >= len(self.entries):
            raise IndexError("Blank deletion index out of range")
        if not self.entries[index].is_blank:
            raise ValueError("Only blank pages can be deleted")
        del self.entries[index]

    def delete_entry(self, index: int) -> None:
        if index < 0 or index >= len(self.entries):
            raise IndexError("Deletion index out of range")
        del self.entries[index]

    def save_preset(self, preset_path: Path) -> None:
        source_order = [entry.source_index for entry in self.entries if entry.source_index is not None]
        deleted_source_pages = sorted(set(range(1, self.source_page_count + 1)) - set(source_order))
        blank_positions = [index for index, entry in enumerate(self.entries) if entry.is_blank]
        payload = {
            "version": 1,
            "source_page_count": self.source_page_count,
            "blank_positions": blank_positions,
            "deleted_source_pages": deleted_source_pages,
        }
        preset_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def apply_preset(self, preset_path: Path) -> None:
        payload = json.loads(preset_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("Unsupported preset version")
        deleted = set(payload.get("deleted_source_pages", []))
        source_entries = [entry for entry in self.entries if entry.source_index not in deleted]
        self.entries = source_entries
        self._blank_counter = 0
        for position in payload.get("blank_positions", []):
            index = min(max(int(position), 0), len(self.entries))
            self.insert_blank(index)

    def export_epub(self, epub_path: Path, overwrite: bool = False, title: str | None = None) -> dict[str, int]:
        counts = self._counts()
        return write_epub_from_pages(
            [entry.page for entry in self.entries],
            epub_path,
            source_path=self.source_path,
            title=title or self.source_path.stem,
            overwrite=overwrite,
            counts=counts,
        )

    def _counts(self) -> dict[str, int]:
        counts: dict[str, int] = {"jpg": 0, "png": 0}
        for entry in self.entries:
            if entry.is_blank:
                counts["blank"] = counts.get("blank", 0) + 1
                continue
            ext = Path(entry.page.image_href or "").suffix.lower().lstrip(".")
            counts[ext] = counts.get(ext, 0) + 1
        return counts

    @property
    def source_page_count(self) -> int:
        return self._source_page_count


def _entry_from_image(image: ImageStream, padding: int) -> LayoutEntry:
    ext, payload = _image_payload(image)
    page_number = f"{image.index:0{padding}d}"
    page = EpubPage(
        index=image.index,
        width=image.width,
        height=image.height,
        image_href=f"images/page-{page_number}.{ext}",
        image_media_type=_media_type_for_ext(ext),
        image_data=payload,
        xhtml_href=f"xhtml/page-{page_number}.xhtml",
        item_id=f"page-{image.index:04d}",
        label=f"Page {image.index}",
    )
    return LayoutEntry(page.label, page, source_index=image.index)


def _image_payload(image: ImageStream) -> tuple[str, bytes]:
    if image.filter_name == "PNG":
        return "png", image.data
    return image_to_archive_member(image)


def _reference_page(entries: list[LayoutEntry], index: int) -> EpubPage:
    for candidate in entries[max(0, index - 1) :: -1]:
        if not candidate.is_blank:
            return candidate.page
    for candidate in entries[index:]:
        if not candidate.is_blank:
            return candidate.page
    raise ValueError("Cannot insert blank page into an empty layout")
