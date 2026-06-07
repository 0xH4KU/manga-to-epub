from __future__ import annotations

import threading
import tkinter as tk


class EpubLayoutBackgroundMixin:
    def _run_background(self, status_message: str, work, on_success, on_failure=None) -> bool:
        if getattr(self, "_busy", False):
            self.status.set("Another operation is already running.")
            return False
        self._busy = True
        self.status.set(status_message)
        self._start_background_progress()
        self.root.update_idletasks()

        def worker() -> None:
            try:
                result = work()
                self.root.after(0, lambda: self._background_done(result, on_success))
            except Exception as exc:
                self.root.after(0, lambda exc=exc: self._background_failed(exc, on_failure))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _start_background_progress(self) -> None:
        progress = getattr(self, "background_progress", None)
        if progress is None:
            return
        progress.configure(mode="indeterminate", maximum=100, value=0)
        progress.pack(side=tk.LEFT, padx=(8, 0))
        progress.start(10)

    def _queue_background_progress_event(self, event: dict) -> None:
        self.root.after(0, lambda event=dict(event): self._background_progress_event(event))

    def _background_progress_event(self, event: dict) -> None:
        progress = getattr(self, "background_progress", None)
        if progress is None:
            return
        total = int(event.get("total") or 0)
        completed = int(event.get("completed") or 0)
        if total <= 0:
            return
        progress.stop()
        progress.pack(side=tk.LEFT, padx=(8, 0))
        progress.configure(mode="determinate", maximum=total, value=max(0, min(completed, total)))
        message = event.get("message")
        if message:
            self.status.set(str(message))

    def _stop_background_progress(self) -> None:
        progress = getattr(self, "background_progress", None)
        if progress is None:
            return
        progress.stop()
        progress.pack_forget()

    def _background_done(self, result, on_success) -> None:
        self._busy = False
        self._stop_background_progress()
        on_success(result)

    def _background_failed(self, exc: Exception, on_failure=None) -> None:
        self._busy = False
        self._stop_background_progress()
        if on_failure is None:
            self._export_failed(exc)
        else:
            on_failure(exc)
