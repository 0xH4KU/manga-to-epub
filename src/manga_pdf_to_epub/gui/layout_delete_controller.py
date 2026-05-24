from __future__ import annotations

from tkinter import messagebox

from .layout_history import CoverState, DeleteHistory
from .layout_support import delete_status
from ..models.layout import LayoutEntry


class EpubLayoutDeleteMixin:
    def _reset_deleted_history(self) -> None:
        self._delete_history().clear()

    def delete_selected_entry(self) -> None:
        if self.model is None:
            return
        index = self.selected_index()
        if index is None:
            return
        entry = self.model.entries[index]
        if not entry.is_blank and not messagebox.askyesno("Delete page", f"Remove {entry.label} from this export?"):
            return
        try:
            self._record_deleted_group([(index, entry)])
            self.model.delete_entry(index)
            select_index = min(index, len(self.model.entries) - 1) if self.model.entries else None
            self._refresh_after_layout_edit(select_index=select_index)
            self.status.set(f"Removed {entry.label} from layout.")
        except Exception as exc:
            messagebox.showerror("Delete page failed", str(exc))

    def recover_last_deleted(self) -> None:
        if self.model is None:
            return
        if not self._delete_history():
            self.unready_selected()
            return
        group, cover_state = self._delete_history().pop()
        restored_indexes = self._restore_entries(group)
        self._restore_cover_state(cover_state)
        self._refresh_after_layout_edit(select_index=restored_indexes[0] if restored_indexes else None)
        if len(group) == 1:
            entry = group[0][1]
            self.status.set(f"Recovered {entry.label} at position {restored_indexes[0] + 1}.")
        else:
            self.status.set(f"Recovered {len(group)} pages.")

    def ask_delete_first(self) -> None:
        count = self._ask_positive_integer("Delete first pages", "How many pages from the start?")
        if count is not None:
            self.quick_delete_first(count)

    def ask_delete_last(self) -> None:
        count = self._ask_positive_integer("Delete last pages", "How many pages from the end?")
        if count is not None:
            self.quick_delete_last(count)

    def ask_delete_range(self) -> None:
        start = self._ask_positive_integer("Delete range", "Start spine position?")
        if start is None:
            return
        end = self._ask_positive_integer("Delete range", "End spine position?")
        if end is not None:
            self.quick_delete_range(start, end)

    def quick_delete_first(self, count: int) -> None:
        if self.model is None:
            return
        self._delete_group(lambda: self.model.delete_first(count), f"Deleted first {count} pages.")

    def quick_delete_last(self, count: int) -> None:
        if self.model is None:
            return
        self._delete_group(lambda: self.model.delete_last(count), f"Deleted last {count} pages.")

    def quick_delete_range(self, start: int, end: int) -> None:
        if self.model is None:
            return
        self._delete_group(lambda: self.model.delete_range(start - 1, end - 1), f"Deleted pages {start}-{end}.")

    def _delete_group(self, delete_action, status_message: str) -> None:
        if self.model is None:
            return
        try:
            cover_state = self._capture_cover_state()
            deleted = delete_action()
            if not deleted:
                return
            if any(not entry.is_blank for _index, entry in deleted):
                labels = ", ".join(entry.label for _index, entry in deleted[:5])
                suffix = "" if len(deleted) <= 5 else f", and {len(deleted) - 5} more"
                if not messagebox.askyesno("Delete pages", f"Remove {labels}{suffix} from this export?"):
                    self._restore_entries(deleted)
                    self._restore_cover_state(cover_state)
                    return
            self._record_deleted_group(deleted, cover_state)
            first_deleted = min(index for index, _entry in deleted)
            select_index = min(first_deleted, len(self.model.entries) - 1) if self.model.entries else None
            self._refresh_after_layout_edit(select_index=select_index)
            self.status.set(delete_status(deleted, status_message))
        except Exception as exc:
            messagebox.showerror("Delete pages failed", str(exc))

    def _restore_entries(self, entries: list[tuple[int, LayoutEntry]]) -> list[int]:
        if self.model is None:
            return []
        restored_indexes: list[int] = []
        for original_index, entry in sorted(entries, key=lambda item: item[0]):
            index = min(max(original_index, 0), len(self.model.entries))
            self.model.entries.insert(index, entry)
            restored_indexes.append(index)
        return restored_indexes

    def _record_deleted_group(
        self,
        deleted: list[tuple[int, LayoutEntry]],
        cover_state: CoverState | None = None,
    ) -> None:
        self._delete_history().push(deleted, cover_state or self._capture_cover_state())

    def _delete_history(self) -> DeleteHistory[LayoutEntry]:
        if not hasattr(self, "deleted_history"):
            history = DeleteHistory()
            for group in getattr(self, "deleted_entries", []):
                history.push(group, None)
            self.deleted_history = history
        return self.deleted_history

    @property
    def deleted_entries(self) -> list[list[tuple[int, LayoutEntry]]]:
        return self._delete_history().legacy_entries()

    @deleted_entries.setter
    def deleted_entries(self, groups: list[list[tuple[int, LayoutEntry]]]) -> None:
        history = DeleteHistory()
        for group in groups:
            history.push(group, None)
        self.deleted_history = history
