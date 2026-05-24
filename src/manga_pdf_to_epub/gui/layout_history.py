from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class CoverState:
    source_index: int | None
    entry_id: str | None


class DeleteHistory(Generic[T]):
    def __init__(self):
        self._items: list[tuple[list[tuple[int, T]], CoverState | None]] = []

    def __bool__(self) -> bool:
        return bool(self._items)

    def push(self, deleted: list[tuple[int, T]], cover_state: CoverState | None) -> None:
        self._items.append((deleted, cover_state))

    def pop(self) -> tuple[list[tuple[int, T]], CoverState | None]:
        if not self._items:
            return [], None
        return self._items.pop()

    def clear(self) -> None:
        self._items.clear()

    def legacy_entries(self) -> list[list[tuple[int, T]]]:
        return [deleted for deleted, _cover_state in self._items]
