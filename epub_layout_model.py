from __future__ import annotations

import json
import dataclasses
from dataclasses import dataclass
from pathlib import Path

import fitz

from pdf_to_cbz_lossless import ImageStream, PdfImageError, image_to_archive_member, images_in_pdf_page_order
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
    def __init__(
        self,
        source_path: Path,
        entries: list[LayoutEntry],
        source_page_count: int | None = None,
        title: str | None = None,
        author: str | None = None,
        language: str = "zh-Hant",
        cover_source_index: int | None = None,
        exclude_cover_from_reading: bool = False,
        cover_entry_id: str | None = None,
    ):
        self.source_path = source_path
        self.entries = entries
        self._source_page_count = source_page_count or max((entry.source_index or 0 for entry in entries), default=0)
        self._blank_counter = sum(1 for entry in entries if entry.is_blank)
        self.title = title or source_path.stem
        self.author = author or ""
        self.language = language or "zh-Hant"
        self.cover_source_index = cover_source_index or self._first_image_source_index()
        self.cover_entry_id = cover_entry_id
        self.exclude_cover_from_reading = exclude_cover_from_reading

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

    def insert_image(self, index: int, image_path: Path) -> None:
        if index < 0 or index > len(self.entries):
            raise IndexError("Image insertion index out of range")
        image_path = Path(image_path)
        ext = image_path.suffix.lower().lstrip(".")
        if ext == "jpeg":
            ext = "jpg"
        if ext not in {"jpg", "png"}:
            raise ValueError("Only JPEG and PNG images can be inserted")
        data = image_path.read_bytes()
        width, height = _image_dimensions(image_path)
        item_number = self._next_external_image_number()
        item_id = f"inserted-{item_number:04d}"
        page = EpubPage(
            index=item_number,
            width=width,
            height=height,
            image_href=f"images/{item_id}.{ext}",
            image_media_type=_media_type_for_ext(ext),
            image_data=data,
            xhtml_href=f"xhtml/{item_id}.xhtml",
            item_id=item_id,
            label=image_path.stem,
        )
        self.entries.insert(index, LayoutEntry(image_path.stem, page))

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
        self._ensure_valid_cover()

    def delete_first(self, count: int) -> list[tuple[int, LayoutEntry]]:
        if count <= 0:
            raise ValueError("Delete count must be greater than zero")
        return self.delete_range(0, min(count, len(self.entries)) - 1)

    def delete_last(self, count: int) -> list[tuple[int, LayoutEntry]]:
        if count <= 0:
            raise ValueError("Delete count must be greater than zero")
        start = max(len(self.entries) - count, 0)
        return self.delete_range(start, len(self.entries) - 1)

    def delete_range(self, start: int, end: int) -> list[tuple[int, LayoutEntry]]:
        if not self.entries:
            raise ValueError("Cannot delete from an empty layout")
        if start < 0 or end < 0:
            raise ValueError("Delete range cannot be negative")
        if start > end:
            raise ValueError("Delete range start must be before end")
        if start >= len(self.entries):
            raise ValueError("Delete range starts after the end of the layout")
        end = min(end, len(self.entries) - 1)
        deleted = [(index, self.entries[index]) for index in range(start, end + 1)]
        del self.entries[start : end + 1]
        self._ensure_valid_cover()
        return deleted

    def normalized_pages(self) -> list[EpubPage]:
        padding = max(4, len(str(len(self.entries))))
        blank_index = 0
        pages: list[EpubPage] = []
        for spine_index, entry in enumerate(self.entries, start=1):
            page_number = f"{spine_index:0{padding}d}"
            if entry.is_blank:
                blank_index += 1
                item_id = f"blank-{blank_index:04d}"
                pages.append(
                    dataclasses.replace(
                        entry.page,
                        index=spine_index,
                        xhtml_href=f"xhtml/{item_id}.xhtml",
                        item_id=item_id,
                    )
                )
                continue

            ext = Path(entry.page.image_href or "").suffix.lower().lstrip(".")
            pages.append(
                dataclasses.replace(
                    entry.page,
                    index=spine_index,
                    image_href=f"images/page-{page_number}.{ext}",
                    xhtml_href=f"xhtml/page-{page_number}.xhtml",
                    item_id=f"page-{spine_index:04d}",
                )
            )
        return pages

    def export_selected_images(self, indexes: list[int], output_dir: Path) -> tuple[list[Path], int]:
        output_dir.mkdir(parents=True, exist_ok=True)
        padding = max(4, len(str(len(self.entries))))
        exported: list[Path] = []
        skipped = 0
        for index in indexes:
            if index < 0 or index >= len(self.entries):
                continue
            entry = self.entries[index]
            if entry.is_blank:
                skipped += 1
                continue
            ext = Path(entry.page.image_href or "").suffix.lower().lstrip(".")
            filename = f"{index + 1:0{padding}d}.{ext}"
            destination = _unique_path(output_dir / filename)
            destination.write_bytes(entry.page.image_data or b"")
            exported.append(destination)
        return exported, skipped

    def normalized_cover_item_id(self) -> str | None:
        for entry, page in zip(self.entries, self.normalized_pages()):
            if self.cover_entry_id is not None and not entry.is_blank and entry.page.item_id == self.cover_entry_id:
                return page.item_id
            if not entry.is_blank and entry.source_index == self.cover_source_index:
                return page.item_id
        return None

    def set_cover(self, source_index: int) -> None:
        entry = next((entry for entry in self.entries if entry.source_index == source_index), None)
        if entry is None or entry.is_blank:
            raise ValueError("Cover must be an image page in the current layout")
        self.cover_source_index = source_index
        self.cover_entry_id = None

    def set_cover_entry(self, entry: LayoutEntry) -> None:
        if entry.is_blank:
            raise ValueError("Cover must be an image page in the current layout")
        if entry.source_index is not None:
            self.set_cover(entry.source_index)
            return
        self.cover_source_index = None
        self.cover_entry_id = entry.page.item_id

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
        if not any(not entry.is_blank for entry in self.entries):
            raise PdfImageError("Cannot export an EPUB without image pages")
        self._ensure_valid_cover()
        counts = self._counts()
        return write_epub_from_pages(
            self.normalized_pages(),
            epub_path,
            source_path=self.source_path,
            title=title or self.title,
            author=self.author or None,
            language=self.language,
            overwrite=overwrite,
            cover_item_id=self.normalized_cover_item_id(),
            exclude_cover_from_reading=self.exclude_cover_from_reading,
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

    def _first_image_source_index(self) -> int | None:
        for entry in self.entries:
            if not entry.is_blank and entry.source_index is not None:
                return entry.source_index
        return None

    def _ensure_valid_cover(self) -> None:
        if self.cover_entry_id is not None:
            if any(not entry.is_blank and entry.page.item_id == self.cover_entry_id for entry in self.entries):
                return
            self.cover_entry_id = None
        if any(not entry.is_blank and entry.source_index == self.cover_source_index for entry in self.entries):
            return
        self.cover_source_index = self._first_image_source_index()

    def _next_external_image_number(self) -> int:
        inserted = [entry.page.item_id for entry in self.entries if entry.source_index is None and not entry.is_blank]
        return len(inserted) + 1


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


def _image_dimensions(image_path: Path) -> tuple[int, int]:
    try:
        with fitz.open(image_path) as doc:
            page = doc[0]
            return int(page.rect.width), int(page.rect.height)
    except Exception as exc:
        raise ValueError(f"Cannot read image dimensions: {image_path}") from exc


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for counter in range(1, 10000):
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError(f"Cannot find available filename for {path}")
