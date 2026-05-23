#!/usr/bin/env python3
"""Small GUI for tuning EPUB blank-page placement before export."""

from __future__ import annotations

import threading
import tkinter as tk
import json
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .fitz_compat import load_fitz
from .epub_layout_commands import app_commands
from .epub_layout_diagnosis_controller import (
    EpubLayoutDiagnosisMixin,
    build_diagnosis_tab,
    initialize_diagnosis_state,
    reset_diagnosis_for_model,
)
from .epub_layout_history import CoverState, DeleteHistory
from .epub_layout_model import LayoutEntry, LayoutModel
from .epub_layout_gui_support import (
    AppCommand,
    PlainTextVariable,
    VirtualBlank,
    delete_status,
    event_from_text_input,
)
from .epub_layout_preview import (
    ThumbnailCache,
    normalize_preview_size,
    preview_entries,
    preview_index_for_selection,
    spread_slots,
    thumbnail_cache_key,
)
from .epub_layout_series_workflow import series_export_preflight
from .epub_series_model import SeriesProject, SeriesVolume


fitz = load_fitz()


class EpubLayoutApp(EpubLayoutDiagnosisMixin):
    def __init__(self, root: tk.Tk):
        self.root = root
        self._configure_window()

        self.model: LayoutModel | None = None
        self.pdf_path: Path | None = None
        self.output_dir = Path.cwd() / "epub_layout_gui_exports"
        self.photo_refs: list[tk.PhotoImage] = []
        self.thumbnail_cache: ThumbnailCache = ThumbnailCache()
        self._pdf_doc = None
        self._pdf_doc_path: Path | None = None
        self.deleted_history: DeleteHistory[LayoutEntry] = DeleteHistory()
        self.ready_status_undo: list[list[tuple[SeriesVolume, str]]] = []
        self.status = tk.StringVar(value="Open a PDF to begin.")
        self.workspace_status = tk.StringVar(value="")
        self.apple_preview = tk.BooleanVar(value=True)
        self.title_var = tk.StringVar(value="")
        self.author_var = tk.StringVar(value="")
        self.language_var = tk.StringVar(value="zh-Hant")
        self.title_label_var = tk.StringVar(value="Title")
        self.author_label_var = tk.StringVar(value="Author")
        self.exclude_cover_var = tk.BooleanVar(value=False)
        self.series_project: SeriesProject | None = None
        self.active_series_volume: SeriesVolume | None = None
        self._busy = False
        self._page_drag_source: int | None = None
        initialize_diagnosis_state(self)

        self._build_ui()
        self._bind_shortcuts()

    def _reset_deleted_history(self) -> None:
        self._delete_history().clear()

    def _configure_window(self) -> None:
        self.root.title("EPUB Layout Lab")
        self.root.geometry("1280x760")
        self.root.minsize(1100, 680)

    @staticmethod
    def _inspector_tab_titles() -> tuple[str, str, str, str]:
        return ("Edit", "Diagnose", "Book", "Series")

    @staticmethod
    def _edit_section_titles() -> tuple[str, str, str]:
        return ("Insert", "Delete", "Repair")

    @staticmethod
    def _series_section_titles() -> tuple[str, str]:
        return ("Review", "Export")

    @staticmethod
    def _metadata_label_texts(series_mode: bool) -> tuple[str, str]:
        if series_mode:
            return ("Series Title", "Series Author")
        return ("Title", "Author")

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Command-z>", lambda _event: self.recover_last_deleted())
        self.root.bind_all("<Control-z>", lambda _event: self.recover_last_deleted())
        self.root.bind_all("<Delete>", self._delete_shortcut)
        self.root.bind_all("<BackSpace>", self._delete_shortcut)
        self.root.bind_all("<Command-Shift-E>", lambda _event: self.export_selected_images())
        self.root.bind_all("<Control-Shift-E>", lambda _event: self.export_selected_images())
        self.root.bind_all("<Command-k>", lambda _event: self.open_command_palette())
        self.root.bind_all("<Control-k>", lambda _event: self.open_command_palette())

    def _delete_shortcut(self, event) -> str | None:
        if event_from_text_input(event):
            return "break"
        self.delete_selected_entry()
        return None

    def _run_background(self, status_message: str, work, on_success) -> bool:
        if getattr(self, "_busy", False):
            self.status.set("Another operation is already running.")
            return False
        self._busy = True
        self.status.set(status_message)
        self.root.update_idletasks()

        def worker() -> None:
            try:
                result = work()
                self.root.after(0, lambda: self._background_done(result, on_success))
            except Exception as exc:
                self.root.after(0, lambda: self._background_failed(exc))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _background_done(self, result, on_success) -> None:
        self._busy = False
        on_success(result)

    def _background_failed(self, exc: Exception) -> None:
        self._busy = False
        self._export_failed(exc)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        toolbar_row = ttk.Frame(toolbar)
        toolbar_row.pack(anchor=tk.CENTER)
        toolbar_buttons = (
            ("Import Series...", self.import_series),
            ("Open PDF", self.open_pdf),
            ("Export EPUB", self.export_epub),
            ("Export Ready Series...", self.export_ready_series),
            ("Open Project...", self.open_project),
            ("Save Project...", self.save_project),
            ("Save Preset", self.save_preset),
            ("Load Preset", self.load_preset),
            ("Command Palette...", self.open_command_palette),
        )
        last_index = len(toolbar_buttons) - 1
        for index, (text, command) in enumerate(toolbar_buttons):
            padx = (0, 0) if index == last_index else (0, 8)
            ttk.Button(toolbar_row, text=text, command=command).pack(side=tk.LEFT, padx=padx)

        main = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        navigation = ttk.Frame(left)
        navigation.pack(fill=tk.BOTH, expand=True)
        navigation.bind("<Configure>", lambda event: self._sync_navigation_mode(available_width=event.width))
        self.series_pane = ttk.Frame(navigation, padding=(0, 0, 6, 0))
        self.series_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(self.series_pane, text="Series volumes").pack(anchor=tk.W)
        self.series_list = tk.Listbox(
            self.series_pane,
            exportselection=False,
            activestyle="dotbox",
            selectmode=tk.EXTENDED,
            width=34,
        )
        self.series_list.pack(fill=tk.BOTH, expand=True, pady=(6, 12))
        self.series_list.bind("<<ListboxSelect>>", lambda _event: self.select_series_volume())
        self.spine_pane = ttk.Frame(navigation, padding=(6, 0, 0, 0))
        self.spine_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(self.spine_pane, text="Spine order").pack(anchor=tk.W)
        self.page_list = tk.Listbox(self.spine_pane, exportselection=False, activestyle="dotbox", selectmode=tk.EXTENDED)
        self.page_list.pack(fill=tk.BOTH, expand=True, pady=(6, 12))
        self.page_list.bind("<<ListboxSelect>>", lambda _event: self.refresh_preview())
        self.page_list.bind("<ButtonPress-1>", self._page_drag_start)
        self.page_list.bind("<ButtonRelease-1>", self._page_drag_release)
        self._sync_navigation_mode()

        center = ttk.Frame(main, padding=8)
        main.add(center, weight=3)
        preview_header = ttk.Frame(center)
        preview_header.pack(fill=tk.X)
        ttk.Label(preview_header, text="RTL spread preview").pack(side=tk.LEFT)
        ttk.Checkbutton(
            preview_header,
            text="Preview Apple Books cover gap",
            variable=self.apple_preview,
            command=self.refresh_preview,
        ).pack(side=tk.RIGHT)
        self.preview = tk.Canvas(center, background="#202020", highlightthickness=0)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.preview.bind("<Configure>", lambda _event: self.refresh_preview())

        inspector = ttk.Frame(main, width=320)
        main.add(inspector, weight=1)
        inspector.pack_propagate(False)
        self.inspector_tabs: dict[str, ttk.Frame] = {}
        self.inspector_tab_buttons: dict[str, ttk.Button] = {}
        self.active_inspector_tab = "Edit"
        self._build_inspector_tab_bar(inspector)
        content = ttk.Frame(inspector)
        content.pack(fill=tk.BOTH, expand=True)
        edit_tab = self._add_inspector_tab(content, "Edit")
        diagnose_tab = self._add_inspector_tab(content, "Diagnose")
        book_tab = self._add_inspector_tab(content, "Book")
        series_tab = self._add_inspector_tab(content, "Series")
        self._build_edit_tab(edit_tab)
        build_diagnosis_tab(self, diagnose_tab)
        self._build_book_tab(book_tab)
        self._build_series_tab(series_tab)
        self._show_inspector_tab("Edit")

        statusbar = ttk.Frame(self.root, padding=(8, 4))
        statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(statusbar, textvariable=self.status).pack(side=tk.LEFT)
        ttk.Label(statusbar, textvariable=self.workspace_status).pack(side=tk.RIGHT)
        self.refresh_workspace_status()

    def _build_inspector_tab_bar(self, parent: ttk.Frame) -> None:
        tabbar = ttk.Frame(parent, padding=(8, 8, 8, 4))
        tabbar.pack(fill=tk.X)
        for title in self._inspector_tab_titles():
            button = ttk.Button(tabbar, text=title, command=lambda tab=title: self._show_inspector_tab(tab))
            button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
            self.inspector_tab_buttons[title] = button

    def _add_inspector_tab(self, container: ttk.Frame, title: str) -> ttk.Frame:
        outer = ttk.Frame(container)
        outer.place(relx=0, rely=0, relwidth=1, relheight=1)
        outer.pack_propagate(False)
        canvas = tk.Canvas(outer, highlightthickness=0, width=300)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        content = ttk.Frame(canvas, padding=(12, 12))
        window_id = canvas.create_window((0, 0), window=content, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        self.inspector_tabs[title] = outer
        return content

    def _show_inspector_tab(self, title: str) -> None:
        if title not in self.inspector_tabs:
            return
        self.active_inspector_tab = title
        self.inspector_tabs[title].tkraise()
        for tab_title, button in getattr(self, "inspector_tab_buttons", {}).items():
            state = tk.DISABLED if tab_title == title else tk.NORMAL
            try:
                button.configure(state=state)
            except tk.TclError:
                pass

    def _build_edit_tab(self, parent: ttk.Frame) -> None:
        self._add_section_label(parent, "Insert")
        self._add_panel_button(parent, "Insert Blank Before", lambda: self.insert_blank(before=True))
        self._add_panel_button(parent, "Insert Blank After", lambda: self.insert_blank(before=False))
        self._add_panel_button(parent, "Quick: Blank Before Cover", self.quick_blank_before_cover)
        self._add_panel_button(parent, "Quick: Blank After Cover", self.quick_blank_after_cover)
        self._add_panel_button(parent, "Insert Image Before", lambda: self.insert_image(before=True))
        self._add_panel_button(parent, "Insert Image After", lambda: self.insert_image(before=False))
        self._add_section_gap(parent)
        self._add_section_label(parent, "Delete")
        self._add_panel_button(parent, "Delete Selected Page", self.delete_selected_entry)
        self._add_section_gap(parent)
        self._add_section_label(parent, "Repair")
        self._add_panel_button(parent, "Recover Last Deleted", self.recover_last_deleted)

    def _build_book_tab(self, parent: ttk.Frame) -> None:
        self._ensure_metadata_label_vars()
        self._add_section_label(parent, "Metadata")
        ttk.Label(parent, textvariable=self.title_label_var).pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(parent, textvariable=self.title_var).pack(fill=tk.X)
        ttk.Label(parent, textvariable=self.author_label_var).pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(parent, textvariable=self.author_var).pack(fill=tk.X)
        ttk.Label(parent, text="Language").pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(parent, textvariable=self.language_var).pack(fill=tk.X)
        self._add_panel_button(parent, "Set Selected As Cover", self.set_selected_as_cover)
        ttk.Checkbutton(
            parent,
            text="Cover only, exclude from pages",
            variable=self.exclude_cover_var,
        ).pack(anchor=tk.W, pady=(8, 0))
        self._add_panel_button(parent, "Export Selected Images...", self.export_selected_images)

    def _build_series_tab(self, parent: ttk.Frame) -> None:
        self._add_section_label(parent, "Review")
        self._add_panel_button(parent, "Mark Selected Volume Ready", self.mark_selected_series_volume_ready)
        self._add_panel_button(parent, "Unready Selected", self.unready_selected)
        self._add_section_gap(parent)
        self._add_section_label(parent, "Export")
        self._add_panel_button(parent, "Export Ready Series...", self.export_ready_series)

    def _add_section_label(self, parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text).pack(anchor=tk.W, pady=(0, 4))

    def _add_section_gap(self, parent: ttk.Frame) -> None:
        ttk.Separator(parent).pack(fill=tk.X, pady=14)

    def _add_panel_button(self, parent: ttk.Frame, text: str, command) -> None:
        ttk.Button(parent, text=text, command=command).pack(fill=tk.X, pady=(6, 0))

    def _commands(self) -> tuple[AppCommand, ...]:
        return app_commands()

    def _matching_commands(self, query: str) -> list[AppCommand]:
        words = [word.casefold() for word in query.split() if word.strip()]
        commands = list(self._commands())
        if not words:
            return commands
        matches = []
        for command in commands:
            haystack = " ".join((command.label, *command.keywords)).casefold()
            if all(word in haystack for word in words):
                matches.append(command)
        return matches

    def _execute_command(self, label: str) -> bool:
        for command in self._commands():
            if command.label == label:
                getattr(self, command.method_name)(*command.args)
                return True
        return False

    def open_command_palette(self) -> None:
        palette = tk.Toplevel(self.root)
        palette.title("Command Palette")
        palette.geometry("420x360")
        palette.transient(self.root)

        query = tk.StringVar()
        entry = ttk.Entry(palette, textvariable=query)
        entry.pack(fill=tk.X, padx=12, pady=(12, 6))

        listbox = tk.Listbox(palette, exportselection=False, activestyle="dotbox")
        listbox.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        def refresh() -> None:
            listbox.delete(0, tk.END)
            for command in self._matching_commands(query.get()):
                listbox.insert(tk.END, command.label)
            if listbox.size():
                listbox.selection_set(0)

        def run_selected(_event=None) -> None:
            selection = listbox.curselection()
            if not selection:
                return
            label = listbox.get(selection[0])
            palette.destroy()
            self._execute_command(label)

        query.trace_add("write", lambda *_args: refresh())
        entry.bind("<Return>", run_selected)
        listbox.bind("<Return>", run_selected)
        listbox.bind("<Double-Button-1>", run_selected)
        palette.bind("<Escape>", lambda _event: palette.destroy())
        refresh()
        entry.focus_set()

    def _workspace_summary(self) -> str:
        if self.model is None:
            page_summary = "No PDF loaded"
        else:
            page_summary = f"Pages: {len(self.model.entries)}"
        if self.series_project is None:
            return f"{page_summary} | Series: 0"
        volumes = self.series_project.volumes
        counts = {"Ready": 0, "Edited": 0, "Failed": 0}
        for volume in volumes:
            if volume.status in counts:
                counts[volume.status] += 1
        return (
            f"{page_summary} | Series: {len(volumes)} | "
            f"Ready: {counts['Ready']} | Edited: {counts['Edited']} | Failed: {counts['Failed']}"
        )

    def refresh_workspace_status(self) -> None:
        if hasattr(self, "workspace_status"):
            self.workspace_status.set(self._workspace_summary())

    def open_pdf(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filename:
            return
        self.pdf_path = Path(filename)
        self._run_background(
            "Loading PDF images...",
            lambda: LayoutModel.from_pdf(self.pdf_path),
            self._open_pdf_done,
        )

    def import_series(self) -> None:
        filenames = filedialog.askopenfilenames(
            title="Import Series PDFs",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filenames:
            return
        self.series_project = SeriesProject.from_pdfs([Path(filename) for filename in filenames])
        self._sync_navigation_mode()
        self._load_metadata_fields()
        self.refresh_series_list()
        self.status.set(f"Imported series with {len(self.series_project.volumes)} volumes.")
        self.refresh_workspace_status()

    def save_project(self) -> None:
        if self.series_project is None:
            return
        if self.model is not None:
            self._store_metadata_fields()
        active_volume = getattr(self, "active_series_volume", None)
        self.series_project.active_volume_number = getattr(active_volume, "volume_number", None)
        filename = filedialog.asksaveasfilename(
            title="Save Series Project",
            defaultextension=".json",
            initialdir=str(Path.cwd()),
            initialfile="series-project.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not filename:
            return
        project_path = Path(filename)
        try:
            payload = self.series_project.to_payload(project_path)
            project_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            self.status.set(f"Saved project: {project_path.name}")
        except Exception as exc:
            messagebox.showerror("Save project failed", str(exc))

    def open_project(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open Series Project",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filename:
            return
        project_path = Path(filename)
        try:
            payload = json.loads(project_path.read_text(encoding="utf-8"))
            self.series_project = SeriesProject.from_payload(payload, project_path)
            self.model = None
            self.pdf_path = None
            self.active_series_volume = None
            self._reset_deleted_history()
            self.ready_status_undo.clear()
            self._reset_preview_cache()
            self._sync_navigation_mode()
            self._load_metadata_fields()
            self.refresh_series_list()
            self._restore_saved_active_series_selection()
            self.refresh_list()
            self.refresh_preview()
            self.status.set(f"Opened project: {project_path.name}")
            self.refresh_workspace_status()
        except Exception as exc:
            messagebox.showerror("Open project failed", str(exc))

    def _restore_saved_active_series_selection(self) -> None:
        if self.series_project is None or not hasattr(self, "series_list"):
            return
        active_number = getattr(self.series_project, "active_volume_number", None)
        if active_number is None:
            return
        for index, volume in enumerate(self.series_project.volumes):
            if volume.volume_number == active_number:
                self.active_series_volume = volume
                self.series_list.selection_clear(0, tk.END)
                self.series_list.selection_set(index)
                return

    def refresh_series_list(self) -> None:
        if not hasattr(self, "series_list"):
            return
        self._sync_navigation_mode()
        self.series_list.delete(0, tk.END)
        if self.series_project is None:
            return
        for volume in self.series_project.volumes:
            self.series_list.insert(
                tk.END,
                f"{volume.status} Vol.{volume.volume_number:02d} {volume.pdf_path.name}",
            )

    def select_series_volume(self) -> None:
        if self.series_project is None or not hasattr(self, "series_list"):
            return
        selection = self.series_list.curselection()
        if not selection:
            return
        volume = self.series_project.volumes[selection[0]]
        try:
            self._load_series_volume(volume)
        except Exception as exc:
            volume.status = "Failed"
            volume.error = str(exc)
            self.refresh_series_list()
            messagebox.showerror("Load series volume failed", str(exc))

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

    def export_ready_series(self) -> None:
        if self.series_project is None:
            return
        if getattr(self, "_busy", False):
            self.status.set("Another operation is already running.")
            return
        output_dir_name = filedialog.askdirectory(
            title="Series output directory",
            initialdir=str(getattr(self, "output_dir", Path.cwd())),
        )
        if not output_dir_name:
            return
        output_dir = Path(output_dir_name)
        preflight = series_export_preflight(self.series_project, output_dir)
        warning_lines = preflight.message_lines
        if warning_lines:
            messagebox.showwarning("Series export preflight", "\n".join(warning_lines))
        self._open_series_export_progress()
        self._run_background(
            "Exporting ready series...",
            lambda: self._export_ready_series_work(output_dir),
            self._series_export_done,
        )

    def validate_series(self) -> None:
        if self.series_project is None:
            return
        output_dir = Path(getattr(self, "output_dir", Path.cwd()))
        summary = self.series_project.validate_all(output_dir)
        self.refresh_series_list()
        self.refresh_workspace_status()
        warning_lines = self._series_warning_lines()
        if warning_lines:
            messagebox.showwarning("Series validation warnings", "\n".join(warning_lines))
        self.status.set(
            f"Series validation: {summary['ready']} ready, {summary['failed']} failed, "
            f"{summary['warnings']} warnings."
        )

    def _series_warning_lines(self) -> list[str]:
        if self.series_project is None:
            return []
        lines: list[str] = []
        for volume in self.series_project.volumes:
            for warning in volume.warnings:
                lines.append(f"Vol.{volume.volume_number:02d}: {warning}")
        return lines[:20]

    def _export_ready_series_work(self, output_dir: Path) -> dict[str, int]:
        summary = {"exported": 0, "failed": 0, "skipped": 0, "warnings": 0}
        if self.series_project is None:
            return summary
        for event in self.series_project.export_ready_iter(output_dir):
            if event["status"] == "summary":
                summary = {
                    "exported": event["exported"],
                    "failed": event["failed"],
                    "skipped": event["skipped"],
                    "warnings": event["warnings"],
                }
                continue
            self.root.after(0, lambda event=event: self._series_export_progress(event))
        return summary

    def _open_series_export_progress(self) -> None:
        self.series_export_progress = {
            "current": "Exporting ready series...",
            "summary": "",
            "close_text": "Exporting...",
        }
        try:
            window = tk.Toplevel(self.root)
            window.title("Series Export")
            window.resizable(False, False)
            current_var = tk.StringVar(value=self.series_export_progress["current"])
            summary_var = tk.StringVar(value="")
            close_text_var = tk.StringVar(value="Exporting...")
            ttk.Label(window, textvariable=current_var, padding=(12, 12, 12, 4)).pack(fill=tk.X)
            ttk.Label(window, textvariable=summary_var, padding=(12, 0, 12, 8)).pack(fill=tk.X)
            close_button = ttk.Button(window, textvariable=close_text_var, command=window.destroy, state=tk.DISABLED)
            close_button.pack(padx=12, pady=(0, 12))
            self.series_export_progress.update(
                {
                    "window": window,
                    "current_var": current_var,
                    "summary_var": summary_var,
                    "close_text_var": close_text_var,
                    "close_button": close_button,
                }
            )
        except Exception:
            pass

    def _set_series_export_progress(self, current: str | None = None, summary: str | None = None) -> None:
        progress = getattr(self, "series_export_progress", None)
        if progress is None:
            return
        if current is not None:
            progress["current"] = current
            current_var = progress.get("current_var")
            if current_var is not None:
                current_var.set(current)
        if summary is not None:
            progress["summary"] = summary
            summary_var = progress.get("summary_var")
            if summary_var is not None:
                summary_var.set(summary)

    def _series_export_progress(self, event: dict) -> None:
        volume_number = event.get("volume_number")
        if volume_number is None:
            return
        status = event.get("status")
        if status == "exported":
            self.status.set(f"Exported Vol.{volume_number:02d}.")
            self._set_series_export_progress(current=f"Exported Vol.{volume_number:02d}.")
            self.refresh_series_list()
        elif status == "failed":
            self.status.set(f"Failed Vol.{volume_number:02d}.")
            self._set_series_export_progress(current=f"Failed Vol.{volume_number:02d}.")
            self.refresh_series_list()
        elif status == "skipped":
            self.status.set(f"Skipped Vol.{volume_number:02d}.")
            self._set_series_export_progress(current=f"Skipped Vol.{volume_number:02d}.")
            self.refresh_series_list()
        elif status == "started":
            self.status.set(f"Exporting Vol.{volume_number:02d}.")
            self._set_series_export_progress(current=f"Exporting Vol.{volume_number:02d}.")

    def _series_export_done(self, summary: dict[str, int]) -> None:
        self.refresh_series_list()
        self.refresh_workspace_status()
        self._finish_series_export_progress(summary)
        self.status.set(
            f"Series exported {summary['exported']} volumes; "
            f"{summary['failed']} failed, {summary['skipped']} skipped, "
            f"{summary.get('warnings', 0)} warnings."
        )

    def _finish_series_export_progress(self, summary: dict[str, int]) -> None:
        text = (
            f"{summary['exported']} exported, {summary['failed']} failed, "
            f"{summary['skipped']} skipped, {summary.get('warnings', 0)} warnings"
        )
        self._set_series_export_progress(current="Series export complete.", summary=text)
        progress = getattr(self, "series_export_progress", None)
        if progress is None:
            return
        progress["close_text"] = "Close"
        close_text_var = progress.get("close_text_var")
        if close_text_var is not None:
            close_text_var.set("Close")
        close_button = progress.get("close_button")
        if close_button is not None:
            close_button.configure(state=tk.NORMAL)

    def _load_series_volume(self, volume: SeriesVolume) -> None:
        self.pdf_path = volume.pdf_path
        self.model = self.series_project.model_for_volume(volume) if self.series_project is not None else None
        self.active_series_volume = volume
        self._reset_deleted_history()
        self._reset_preview_cache()
        self._load_metadata_fields()
        self.refresh_list()
        self.page_list.selection_clear(0, tk.END)
        if self.model is not None and self.model.entries:
            self.page_list.selection_set(0)
        self.status.set(f"Loaded {self.series_project.generated_title(volume)}.")
        self.refresh_workspace_status()
        self.refresh_preview()

    def _open_pdf_done(self, model: LayoutModel) -> None:
        self.model = model
        reset_diagnosis_for_model(self, model)
        self.series_project = None
        self.active_series_volume = None
        self._sync_navigation_mode()
        self._reset_deleted_history()
        self._reset_preview_cache()
        self._load_metadata_fields()
        self.refresh_list()
        self.page_list.selection_clear(0, tk.END)
        if self.model.entries:
            self.page_list.selection_set(0)
        self.status.set(f"Loaded {self.pdf_path.name}: {len(self.model.entries)} pages")
        self.refresh_workspace_status()
        self.refresh_preview()

    def refresh_list(self, preserve_yview: bool = False) -> None:
        if self.model is None:
            self.refresh_workspace_status()
            return
        yview_start = self.page_list.yview()[0] if preserve_yview else None
        self.page_list.delete(0, tk.END)
        for i, entry in enumerate(self.model.entries, start=1):
            marker = "[blank]" if entry.is_blank else "[page]"
            cover = " [cover]" if self._is_cover_entry(entry) else ""
            self.page_list.insert(tk.END, f"{i:04d} {marker}{cover} {entry.label}")
        if yview_start is not None:
            self.page_list.yview_moveto(yview_start)
        self.refresh_workspace_status()

    def _sync_navigation_mode(self, available_width: int | None = None) -> None:
        if not hasattr(self, "series_pane") or not hasattr(self, "spine_pane"):
            return
        series_mode = getattr(self, "series_project", None) is not None
        if series_mode:
            if self._navigation_uses_columns(available_width):
                self._pack_navigation_pane(self.series_pane, side=tk.LEFT, fill=tk.BOTH, expand=True)
                self._pack_navigation_pane(self.spine_pane, side=tk.LEFT, fill=tk.BOTH, expand=True)
            else:
                self._pack_navigation_pane(self.series_pane, side=tk.TOP, fill=tk.BOTH, expand=True)
                self._pack_navigation_pane(self.spine_pane, side=tk.TOP, fill=tk.BOTH, expand=True)
        else:
            self.series_pane.pack_forget()
            self._pack_navigation_pane(self.spine_pane, side=tk.LEFT, fill=tk.BOTH, expand=True)

    @staticmethod
    def _navigation_uses_columns(available_width: int | None) -> bool:
        if available_width is None:
            return False
        return available_width >= 680

    @staticmethod
    def _pack_navigation_pane(pane, **kwargs) -> None:
        try:
            pane.pack_forget()
        except Exception:
            pass
        pane.pack(**kwargs)

    def selected_index(self) -> int | None:
        selection = self.page_list.curselection()
        return selection[0] if selection else None

    def selected_indexes(self) -> list[int]:
        return list(self.page_list.curselection())

    def _page_drag_start(self, event) -> None:
        if self.model is None or not self.model.entries:
            self._page_drag_source = None
            return
        index = self.page_list.nearest(event.y)
        if index < 0 or index >= len(self.model.entries):
            self._page_drag_source = None
            return
        self._page_drag_source = index

    def _page_drag_release(self, event) -> None:
        if self.model is None or self._page_drag_source is None:
            return
        from_index = self._page_drag_source
        self._page_drag_source = None
        if not self.model.entries:
            return
        to_index = self.page_list.nearest(event.y)
        to_index = min(max(to_index, 0), len(self.model.entries) - 1)
        if from_index == to_index:
            return
        try:
            label = self.model.entries[from_index].label
            final_index = self.model.move_entry(from_index, to_index)
            self._refresh_after_layout_edit(select_index=final_index)
            self.status.set(f"Moved {label} to position {final_index + 1}.")
        except Exception as exc:
            messagebox.showerror("Move page failed", str(exc))

    def insert_blank(self, before: bool) -> None:
        if self.model is None:
            return
        selected = self.selected_index()
        index = selected if selected is not None else len(self.model.entries)
        if not before:
            index += 1
        try:
            self.model.insert_blank(index)
            self._refresh_after_layout_edit(select_index=index)
            self.status.set(f"Inserted blank page at position {index + 1}.")
        except Exception as exc:
            messagebox.showerror("Insert blank failed", str(exc))

    def insert_image(self, before: bool) -> None:
        if self.model is None:
            return
        filename = filedialog.askopenfilename(
            title="Insert Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filename:
            return
        selected = self.selected_index()
        index = selected if selected is not None else len(self.model.entries)
        if not before:
            index += 1
        try:
            self.model.insert_image(index, Path(filename))
            self._refresh_after_layout_edit(select_index=index)
            self.status.set(f"Inserted image: {Path(filename).name}")
        except Exception as exc:
            messagebox.showerror("Insert image failed", str(exc))

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

    def quick_blank_before_cover(self) -> None:
        if self.model is None:
            return
        index = self._cover_entry_index()
        if index is None:
            index = 0
        self.model.insert_blank(index)
        self._refresh_after_layout_edit(select_index=index)
        self.status.set("Inserted one blank page before cover.")

    def quick_blank_after_cover(self) -> None:
        if self.model is None:
            return
        index = self._cover_entry_index()
        if index is None:
            index = 0
        index += 1
        self.model.insert_blank(index)
        self._refresh_after_layout_edit(select_index=index)
        self.status.set("Inserted one blank page after cover.")

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

    def set_selected_as_cover(self) -> None:
        if self.model is None:
            return
        index = self.selected_index()
        if index is None:
            return
        entry = self.model.entries[index]
        if entry.is_blank:
            messagebox.showerror("Set cover failed", "Cover must be an image page.")
            return
        try:
            self.model.set_cover_entry(entry)
            self.refresh_list(preserve_yview=True)
            self.status.set(f"Set {entry.label} as cover.")
            self._mark_active_volume_edited()
        except Exception as exc:
            messagebox.showerror("Set cover failed", str(exc))

    def export_selected_images(self) -> None:
        if self.model is None:
            return
        indexes = self.selected_indexes()
        if not indexes:
            return
        output_dir_name = filedialog.askdirectory(title="Export selected images", initialdir=str(Path.cwd()))
        if not output_dir_name:
            return
        try:
            exported, skipped = self.model.export_selected_images(indexes, Path(output_dir_name))
            self.status.set(f"Exported {len(exported)} images; skipped {skipped} blank pages.")
            if not exported:
                messagebox.showinfo("Export selected images", "No exportable images selected.")
        except Exception as exc:
            messagebox.showerror("Export selected images failed", str(exc))

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

    def _capture_cover_state(self) -> CoverState:
        if self.model is None:
            return CoverState(None, None)
        return CoverState(
            getattr(self.model, "cover_source_index", None),
            getattr(self.model, "cover_entry_id", None),
        )

    def _restore_cover_state(self, state: CoverState | None) -> None:
        if self.model is None or state is None:
            return
        self.model.cover_source_index = state.source_index
        self.model.cover_entry_id = state.entry_id

    def _cover_entry_index(self) -> int | None:
        if self.model is None:
            return None
        for index, entry in enumerate(self.model.entries):
            if self._is_cover_entry(entry):
                return index
        return None

    def _refresh_after_layout_edit(
        self,
        select_index: int | None = None,
        preserve_yview: bool = True,
        mark_edited: bool = True,
    ) -> None:
        self.refresh_list(preserve_yview=preserve_yview)
        self.page_list.selection_clear(0, tk.END)
        if select_index is not None:
            self.page_list.selection_set(select_index)
        self.refresh_preview()
        if mark_edited:
            self._mark_active_volume_edited()

    def _mark_active_volume_edited(self) -> None:
        volume = getattr(self, "active_series_volume", None)
        if getattr(self, "series_project", None) is None or volume is None:
            return
        volume.status = "Edited"
        volume.error = None
        self.refresh_series_list()
        self._restore_active_series_selection()
        self.refresh_workspace_status()

    def _restore_active_series_selection(self) -> None:
        if self.series_project is None or not hasattr(self, "series_list"):
            return
        volume = getattr(self, "active_series_volume", None)
        if volume is None:
            return
        try:
            index = self.series_project.volumes.index(volume)
        except ValueError:
            return
        self.series_list.selection_clear(0, tk.END)
        self.series_list.selection_set(index)

    def _ask_positive_integer(self, title: str, prompt: str) -> int | None:
        return simpledialog.askinteger(title, prompt, minvalue=1, parent=self.root)

    def export_epub(self) -> None:
        if self.model is None or self.pdf_path is None:
            return
        self._store_metadata_fields()
        self.output_dir.mkdir(exist_ok=True)
        default = self.pdf_path.with_suffix(".epub").name
        filename = filedialog.asksaveasfilename(
            title="Export EPUB",
            defaultextension=".epub",
            initialdir=str(self.output_dir),
            initialfile=default,
            filetypes=[("EPUB files", "*.epub"), ("All files", "*.*")],
        )
        if not filename:
            return
        epub_path = Path(filename)
        self._run_background(
            "Exporting EPUB...",
            lambda: self.model.export_epub(epub_path, overwrite=True),
            lambda counts: self._export_done(epub_path, counts),
        )

    def save_preset(self) -> None:
        if self.model is None:
            return
        self._store_metadata_fields()
        filename = filedialog.asksaveasfilename(
            title="Save Layout Preset",
            defaultextension=".json",
            initialdir=str(Path.cwd()),
            initialfile="layout-preset.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            self.model.save_preset(Path(filename))
            self.status.set(f"Saved preset: {Path(filename).name}")
        except Exception as exc:
            messagebox.showerror("Save preset failed", str(exc))

    def load_preset(self) -> None:
        if self.model is None:
            return
        filename = filedialog.askopenfilename(
            title="Load Layout Preset",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filename:
            return
        try:
            preset_path = Path(filename)
            if self.series_project is not None:
                self._load_preset_for_series(preset_path)
            else:
                self._load_preset_for_current_model(preset_path)
        except Exception as exc:
            messagebox.showerror("Load preset failed", str(exc))

    def _load_preset_for_current_model(self, preset_path: Path) -> None:
        if self.model is None:
            return
        self.model.apply_preset(preset_path)
        self._load_metadata_fields()
        self.refresh_list()
        self.page_list.selection_clear(0, tk.END)
        if self.model.entries:
            self.page_list.selection_set(0)
        self.refresh_preview()
        self.status.set(f"Loaded preset: {preset_path.name}")

    def _load_preset_for_series(self, preset_path: Path) -> None:
        if self.series_project is None:
            return
        scope = simpledialog.askstring(
            "Apply Preset to Volumes",
            "Volumes to apply preset to (examples: 1,2,7 or 1-7 or all):",
            parent=getattr(self, "root", None),
        )
        if scope is None or not scope.strip():
            return
        target_volumes = self.series_project.volumes_for_scope(scope)
        if not target_volumes:
            self.status.set("No volumes matched preset scope.")
            return
        active_volume = getattr(self, "active_series_volume", None)
        active_was_updated = False
        for volume in target_volumes:
            model = self.series_project.model_for_volume(volume)
            model.apply_preset(preset_path)
            model.title = self.series_project.generated_title(volume)
            model.author = self.series_project.author
            model.language = self.series_project.language
            volume.status = "Edited"
            volume.error = None
            if volume is active_volume:
                active_was_updated = True
        self.refresh_series_list()
        self._restore_active_series_selection()
        self.refresh_workspace_status()
        if active_was_updated:
            self._load_metadata_fields()
            self.refresh_list()
            self.page_list.selection_clear(0, tk.END)
            if self.model is not None and self.model.entries:
                self.page_list.selection_set(0)
            self.refresh_preview()
        self.status.set(f"Loaded preset for {len(target_volumes)} volumes: {preset_path.name}")

    def _load_metadata_fields(self) -> None:
        if self.model is None:
            if self.series_project is None:
                return
            title = self.series_project.title
            author = self.series_project.author
            language = self.series_project.language
            exclude_cover = False
        elif self.series_project is not None:
            title = self.series_project.title
            author = self.series_project.author
            language = self.series_project.language
            exclude_cover = self.model.exclude_cover_from_reading
        else:
            title = self.model.title
            author = self.model.author
            language = self.model.language
            exclude_cover = self.model.exclude_cover_from_reading
        self._sync_metadata_label_texts()
        self.title_var.set(title)
        self.author_var.set(author)
        self.language_var.set(language)
        self.exclude_cover_var.set(exclude_cover)

    def _store_metadata_fields(self) -> None:
        if self.model is None:
            return
        title = self.title_var.get().strip()
        author = self.author_var.get().strip()
        language = self.language_var.get().strip() or "zh-Hant"
        if self.series_project is not None:
            self.series_project.title = title or self.series_project.title
            self.series_project.author = author
            self.series_project.language = language
            active_volume = getattr(self, "active_series_volume", None)
            if active_volume is not None and hasattr(self.series_project, "generated_title"):
                self.model.title = self.series_project.generated_title(active_volume)
            self.model.author = self.series_project.author
            self.model.language = self.series_project.language
        else:
            self.model.title = title or self.model.source_path.stem
            self.model.author = author
            self.model.language = language
        self.model.exclude_cover_from_reading = self.exclude_cover_var.get()

    def _sync_metadata_label_texts(self) -> None:
        self._ensure_metadata_label_vars()
        title_label, author_label = self._metadata_label_texts(self.series_project is not None)
        if hasattr(self, "title_label_var"):
            self.title_label_var.set(title_label)
        if hasattr(self, "author_label_var"):
            self.author_label_var.set(author_label)

    def _ensure_metadata_label_vars(self) -> None:
        if not hasattr(self, "title_label_var"):
            self.title_label_var = PlainTextVariable("Title")
        if not hasattr(self, "author_label_var"):
            self.author_label_var = PlainTextVariable("Author")

    def _is_cover_entry(self, entry: LayoutEntry) -> bool:
        if self.model is None:
            return False
        if entry.is_blank:
            return False
        cover_entry_id = getattr(self.model, "cover_entry_id", None)
        if cover_entry_id is not None:
            return entry.page.item_id == cover_entry_id
        return entry.source_index == getattr(self.model, "cover_source_index", None)

    def _export_done(self, epub_path: Path, counts: dict[str, int]) -> None:
        self.status.set(f"Exported {epub_path.name}: {counts['total']} spine items.")
        messagebox.showinfo("Export complete", f"Exported:\n{epub_path}")

    def _export_failed(self, exc: Exception) -> None:
        self.status.set("Export failed.")
        messagebox.showerror("Export failed", str(exc))

    def refresh_preview(self) -> None:
        self.preview.delete("all")
        self.photo_refs.clear()
        if self.model is None or not self.model.entries:
            return
        selected = self.selected_index()
        if selected is None:
            selected = 0
        preview_entries = self._preview_entries()
        preview_selected = self._preview_index_for_selection(selected)
        pair_start = preview_selected if preview_selected % 2 == 0 else preview_selected - 1
        entries = preview_entries[pair_start : pair_start + 2]

        width = max(400, self.preview.winfo_width())
        height = max(300, self.preview.winfo_height())
        gap = 12
        page_w = (width - gap * 3) // 2
        page_h = height - gap * 2

        slots = self._spread_slots(pair_start, gap, page_w)
        for entry, (x, y) in zip(entries, slots):
            self._draw_entry(entry, x, y, page_w, page_h)

    def _preview_index_for_selection(self, selected: int) -> int:
        return preview_index_for_selection(selected, self._uses_apple_cover_gap())

    def _spread_slots(self, pair_start: int, gap: int, page_w: int) -> list[tuple[int, int]]:
        return spread_slots(pair_start, gap, page_w, self._uses_apple_cover_gap())

    def _preview_entries(self):
        if self.model is None:
            return []
        return preview_entries(list(self.model.entries), self._uses_apple_cover_gap())

    def _uses_apple_cover_gap(self) -> bool:
        if self.model is None or not self.model.entries:
            return False
        return self.apple_preview.get()

    def _draw_entry(self, entry, x: int, y: int, max_w: int, max_h: int) -> None:
        self.preview.create_rectangle(x, y, x + max_w, y + max_h, fill="#ffffff", outline="#707070")
        if entry.is_blank:
            fill = "#a0a0a0" if isinstance(entry, VirtualBlank) else "#606060"
            self.preview.create_text(x + max_w // 2, y + max_h // 2, text=entry.label, fill=fill)
            return
        if getattr(entry, "source_index", None) is None:
            photo = self._thumbnail_for_entry(entry, max_w, max_h)
        else:
            photo = self._thumbnail_for_page(entry.page.index, max_w, max_h)
        if photo is None:
            self.preview.create_text(x + max_w // 2, y + max_h // 2, text=entry.label, fill="#202020")
            return
        self.photo_refs.append(photo)
        image_x = x + (max_w - photo.width()) // 2
        image_y = y + (max_h - photo.height()) // 2
        self.preview.create_image(image_x, image_y, anchor=tk.NW, image=photo)
        self.preview.create_text(x + 8, y + 16, text=entry.label, anchor=tk.W, fill="#ffffff")

    def _thumbnail_for_page(self, page_index: int, max_w: int, max_h: int) -> tk.PhotoImage | None:
        if self.pdf_path is None:
            return None
        bucket_w, bucket_h = normalize_preview_size(max_w, max_h)
        cache_key = ("pdf", page_index, bucket_w, bucket_h)
        cached = self.thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            doc = self._pdf_document()
            page = doc[page_index - 1]
            zoom = min(max_w / page.rect.width, max_h / page.rect.height)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = tk.PhotoImage(data=pix.tobytes("png"))
            self.thumbnail_cache[cache_key] = image
            return image
        except Exception:
            if hasattr(self, "status"):
                self.status.set(f"Preview failed for page {page_index}.")
            return None

    def _pdf_document(self):
        if self.pdf_path is None:
            return None
        if getattr(self, "_pdf_doc", None) is not None and self._pdf_doc_path == self.pdf_path:
            return self._pdf_doc
        self._close_pdf_document()
        self._pdf_doc = fitz.open(self.pdf_path)
        self._pdf_doc_path = self.pdf_path
        return self._pdf_doc

    def _close_pdf_document(self) -> None:
        doc = getattr(self, "_pdf_doc", None)
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
        self._pdf_doc = None
        self._pdf_doc_path = None

    def _reset_preview_cache(self) -> None:
        if not isinstance(getattr(self, "thumbnail_cache", None), ThumbnailCache):
            self.thumbnail_cache = ThumbnailCache()
        else:
            self.thumbnail_cache.clear()
        self._close_pdf_document()

    def _thumbnail_for_entry(self, entry, max_w: int, max_h: int) -> tk.PhotoImage | None:
        cache_key = self._thumbnail_cache_key(entry, max_w, max_h)
        cached = self.thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            image = tk.PhotoImage(data=entry.page.image_data)
            scale = max(1, int(max(image.width() / max_w, image.height() / max_h, 1)))
            if scale > 1:
                image = image.subsample(scale, scale)
            self.thumbnail_cache[cache_key] = image
            return image
        except Exception:
            return None

    def _thumbnail_cache_key(self, entry, max_w: int, max_h: int):
        return thumbnail_cache_key(entry, max_w, max_h)

def main() -> int:
    root = tk.Tk()
    EpubLayoutApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
