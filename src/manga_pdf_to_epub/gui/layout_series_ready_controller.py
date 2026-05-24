from __future__ import annotations

from ..models.series import SeriesVolume


class EpubLayoutSeriesReadyMixin:
    def mark_selected_series_volume_ready(self) -> None:
        if self.series_project is None or not hasattr(self, "series_list"):
            return
        selection = self.series_list.curselection()
        if not selection:
            return
        selected_volumes = [self.series_project.volumes[index] for index in selection]
        self._record_ready_status_undo(selected_volumes)
        for volume in selected_volumes:
            self.series_project.mark_ready(volume)
        self.refresh_series_list()
        self.refresh_workspace_status()
        if len(selected_volumes) == 1:
            self.status.set(f"Marked Vol.{selected_volumes[0].volume_number:02d} ready.")
        else:
            self.status.set(f"Marked {len(selected_volumes)} volumes ready.")

    def _record_ready_status_undo(self, volumes: list[SeriesVolume]) -> None:
        if not hasattr(self, "ready_status_undo"):
            self.ready_status_undo = []
        self.ready_status_undo.append([(volume, volume.status) for volume in volumes])

    def unready_selected(self) -> bool:
        undo_stack = getattr(self, "ready_status_undo", [])
        if not undo_stack:
            return False
        selected_volumes = self._selected_series_volumes()
        if selected_volumes:
            return self._unready_selected_volumes(selected_volumes)
        return self._unready_latest_batch()

    def undo_ready_mark(self) -> bool:
        return self.unready_selected()

    def _selected_series_volumes(self) -> list[SeriesVolume]:
        if self.series_project is None or not hasattr(self, "series_list"):
            return []
        selection = self.series_list.curselection()
        return [
            self.series_project.volumes[index]
            for index in selection
            if 0 <= index < len(self.series_project.volumes)
        ]

    def _unready_selected_volumes(self, selected_volumes: list[SeriesVolume]) -> bool:
        undo_stack = getattr(self, "ready_status_undo", [])
        pending_volume_ids = {id(volume) for volume in selected_volumes}
        restored_statuses: list[tuple[SeriesVolume, str]] = []
        revised_stack = [list(batch) for batch in undo_stack]

        for batch_index in range(len(revised_stack) - 1, -1, -1):
            batch = revised_stack[batch_index]
            remaining_statuses: list[tuple[SeriesVolume, str]] = []
            for volume, previous_status in batch:
                if id(volume) in pending_volume_ids:
                    volume.status = previous_status
                    volume.error = None
                    restored_statuses.append((volume, previous_status))
                    pending_volume_ids.remove(id(volume))
                else:
                    remaining_statuses.append((volume, previous_status))
            revised_stack[batch_index] = remaining_statuses
            if not pending_volume_ids:
                break

        if not restored_statuses:
            self.status.set("No selected ready marks to undo.")
            return False

        self.ready_status_undo = [batch for batch in revised_stack if batch]
        self.refresh_series_list()
        self.refresh_workspace_status()
        if len(restored_statuses) == 1:
            volume = restored_statuses[0][0]
            self.status.set(f"Restored Vol.{volume.volume_number:02d} status.")
        else:
            self.status.set(f"Restored {len(restored_statuses)} selected volume statuses.")
        return True

    def _unready_latest_batch(self) -> bool:
        undo_stack = getattr(self, "ready_status_undo", [])
        if not undo_stack:
            return False
        previous_statuses = undo_stack.pop()
        for volume, previous_status in previous_statuses:
            volume.status = previous_status
            volume.error = None
        self.refresh_series_list()
        self.refresh_workspace_status()
        if len(previous_statuses) == 1:
            volume = previous_statuses[0][0]
            self.status.set(f"Restored Vol.{volume.volume_number:02d} status.")
        else:
            self.status.set(f"Restored {len(previous_statuses)} volume statuses.")
        return True
