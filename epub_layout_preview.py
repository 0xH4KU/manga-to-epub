from __future__ import annotations

from collections import OrderedDict
from typing import Any

from epub_layout_gui_support import VirtualBlank


class ThumbnailCache(OrderedDict):
    def __init__(self, max_entries: int = 128):
        super().__init__()
        self.max_entries = max_entries

    def __setitem__(self, key: Any, value: Any) -> None:
        if key in self:
            super().__delitem__(key)
        super().__setitem__(key, value)
        self._evict()

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self:
            return default
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def _evict(self) -> None:
        while len(self) > self.max_entries:
            self.popitem(last=False)


def normalize_preview_size(width: int, height: int, bucket: int = 50) -> tuple[int, int]:
    return (_round_up(width, bucket), _round_up(height, bucket))


def _round_up(value: int, bucket: int) -> int:
    return max(bucket, ((max(1, value) + bucket - 1) // bucket) * bucket)


def preview_index_for_selection(selected: int, uses_apple_cover_gap: bool) -> int:
    if uses_apple_cover_gap and selected >= 1:
        return selected + 1
    return selected


def spread_slots(pair_start: int, gap: int, page_w: int, uses_apple_cover_gap: bool) -> list[tuple[int, int]]:
    left = (gap, gap)
    right = (gap * 2 + page_w, gap)
    if uses_apple_cover_gap and pair_start == 0:
        return [left, right]
    return [right, left]


def preview_entries(entries: list, uses_apple_cover_gap: bool):
    if uses_apple_cover_gap and entries:
        cover_gap = VirtualBlank("Virtual Apple Books cover gap")
        return [entries[0], cover_gap, *entries[1:]]
    return list(entries)


def thumbnail_cache_key(entry, max_w: int, max_h: int):
    bucket_w, bucket_h = normalize_preview_size(max_w, max_h)
    source_index = getattr(entry, "source_index", None)
    if source_index is not None:
        return ("source", source_index, bucket_w, bucket_h)
    page = getattr(entry, "page", None)
    item_id = getattr(page, "item_id", None)
    if item_id is not None:
        return ("entry", item_id, bucket_w, bucket_h)
    return ("entry", id(entry), bucket_w, bucket_h)
