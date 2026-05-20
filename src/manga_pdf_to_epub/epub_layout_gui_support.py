from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from epub_layout_model import LayoutEntry


@dataclass(frozen=True)
class AppCommand:
    label: str
    method_name: str
    args: tuple = ()
    keywords: tuple[str, ...] = ()


class VirtualBlank:
    def __init__(self, label: str):
        self.label = label
        self.is_blank = True


class PlainTextVariable:
    def __init__(self, value: str):
        self.value = value

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


def event_from_text_input(event: Any) -> bool:
    widget = getattr(event, "widget", None)
    if widget is None:
        return False
    try:
        widget_class = widget.winfo_class()
    except Exception:
        return False
    return widget_class in {"Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"}


def delete_status(deleted: list[tuple[int, LayoutEntry]], fallback: str) -> str:
    if not deleted:
        return fallback
    blank_count = sum(1 for _index, entry in deleted if entry.is_blank)
    image_count = len(deleted) - blank_count
    image_word = "image" if image_count == 1 else "images"
    blank_word = "blank" if blank_count == 1 else "blanks"
    return f"Deleted {len(deleted)} entries: {image_count} {image_word}, {blank_count} {blank_word}."
