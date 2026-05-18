#!/usr/bin/env python3
"""Small GUI for tuning EPUB blank-page placement before export."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import fitz

from epub_batch_model import BatchProject
from epub_layout_model import LayoutEntry, LayoutModel


class EpubLayoutApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("EPUB Layout Lab")
        self.root.geometry("1120x720")

        self.model: LayoutModel | None = None
        self.pdf_path: Path | None = None
        self.output_dir = Path.cwd() / "epub_layout_gui_exports"
        self.photo_refs: list[tk.PhotoImage] = []
        self.thumbnail_cache: dict[int, tk.PhotoImage] = {}
        self.deleted_entries: list[list[tuple[int, LayoutEntry]]] = []
        self.status = tk.StringVar(value="Open a PDF to begin.")
        self.apple_preview = tk.BooleanVar(value=True)
        self.title_var = tk.StringVar(value="")
        self.author_var = tk.StringVar(value="")
        self.language_var = tk.StringVar(value="zh-Hant")
        self.exclude_cover_var = tk.BooleanVar(value=False)
        self.batch_project: BatchProject | None = None
        self.batch_output_dir: Path | None = None
        self._busy = False

        self._build_ui()
        self._bind_shortcuts()

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Command-z>", lambda _event: self.recover_last_deleted())
        self.root.bind_all("<Control-z>", lambda _event: self.recover_last_deleted())
        self.root.bind_all("<Delete>", lambda _event: self.delete_selected_entry())
        self.root.bind_all("<BackSpace>", lambda _event: self.delete_selected_entry())
        self.root.bind_all("<Command-Shift-E>", lambda _event: self.export_selected_images())
        self.root.bind_all("<Control-Shift-E>", lambda _event: self.export_selected_images())

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
        ttk.Button(toolbar, text="Open PDF", command=self.open_pdf).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Export EPUB", command=self.export_epub).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(toolbar, text="Save Preset", command=self.save_preset).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(toolbar, text="Load Preset", command=self.load_preset).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(toolbar, text="Batch Apply", command=self.batch_apply_preset).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(toolbar, textvariable=self.status).pack(side=tk.LEFT, padx=12)

        main = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        ttk.Label(left, text="Spine order").pack(anchor=tk.W)
        self.page_list = tk.Listbox(left, exportselection=False, activestyle="dotbox", selectmode=tk.EXTENDED)
        self.page_list.pack(fill=tk.BOTH, expand=True, pady=(6, 12))
        self.page_list.bind("<<ListboxSelect>>", lambda _event: self.refresh_preview())
        ttk.Label(left, text="Batch queue").pack(anchor=tk.W)
        self.batch_list = tk.Listbox(left, exportselection=False, height=7)
        self.batch_list.pack(fill=tk.X, pady=(6, 0))

        center = ttk.Frame(main, padding=8)
        main.add(center, weight=3)
        preview_header = ttk.Frame(center)
        preview_header.pack(fill=tk.X)
        ttk.Label(preview_header, text="RTL spread preview").pack(side=tk.LEFT)
        ttk.Checkbutton(
            preview_header,
            text="Apple Books-like cover-right gap",
            variable=self.apple_preview,
            command=self.refresh_preview,
        ).pack(side=tk.RIGHT)
        self.preview = tk.Canvas(center, background="#202020", highlightthickness=0)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.preview.bind("<Configure>", lambda _event: self.refresh_preview())

        right = ttk.Frame(main, padding=8)
        main.add(right, weight=1)
        ttk.Label(right, text="Insert").pack(anchor=tk.W)
        ttk.Button(right, text="Insert Blank Before", command=lambda: self.insert_blank(before=True)).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Insert Blank After", command=lambda: self.insert_blank(before=False)).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Insert Image Before", command=lambda: self.insert_image(before=True)).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Insert Image After", command=lambda: self.insert_image(before=False)).pack(fill=tk.X, pady=(8, 0))
        ttk.Separator(right).pack(fill=tk.X, pady=16)
        ttk.Label(right, text="Delete").pack(anchor=tk.W)
        ttk.Button(right, text="Delete Selected Page", command=self.delete_selected_entry).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Recover Last Deleted", command=self.recover_last_deleted).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Quick: Blank Before Cover", command=self.quick_blank_before_cover).pack(fill=tk.X)
        ttk.Button(right, text="Quick: Blank After Cover", command=self.quick_blank_after_cover).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Delete First...", command=self.ask_delete_first).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Delete Last...", command=self.ask_delete_last).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Delete Range...", command=self.ask_delete_range).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Normalize Export Order", command=self.normalize_export_order).pack(fill=tk.X, pady=(8, 0))
        ttk.Separator(right).pack(fill=tk.X, pady=16)
        ttk.Label(right, text="Metadata").pack(anchor=tk.W)
        ttk.Label(right, text="Title").pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(right, textvariable=self.title_var).pack(fill=tk.X)
        ttk.Label(right, text="Author").pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(right, textvariable=self.author_var).pack(fill=tk.X)
        ttk.Label(right, text="Language").pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(right, textvariable=self.language_var).pack(fill=tk.X)
        ttk.Button(right, text="Set Selected As Cover", command=self.set_selected_as_cover).pack(fill=tk.X, pady=(8, 0))
        ttk.Checkbutton(
            right,
            text="Cover only, exclude from pages",
            variable=self.exclude_cover_var,
        ).pack(anchor=tk.W, pady=(8, 0))
        ttk.Button(right, text="Export Selected Images...", command=self.export_selected_images).pack(fill=tk.X, pady=(8, 0))
        ttk.Separator(right).pack(fill=tk.X, pady=16)
        ttk.Label(right, text="Batch project").pack(anchor=tk.W)
        ttk.Button(right, text="Use Current Layout As Template", command=self.use_current_layout_as_batch_template).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Load Template Preset...", command=self.load_batch_template_from_preset).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Add PDFs...", command=self.add_batch_pdfs).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Validate Batch...", command=self.validate_batch).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Export Ready...", command=self.export_ready_batch).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Export All...", command=self.export_all_batch).pack(fill=tk.X, pady=(8, 0))
        ttk.Separator(right).pack(fill=tk.X, pady=16)
        ttk.Label(
            right,
            text=(
                "Images are exported losslessly.\n"
                "Blank pages only change EPUB spine order.\n"
                "Apple Books-like preview inserts a virtual blank on the right of the cover."
            ),
            wraplength=220,
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

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

    def _open_pdf_done(self, model: LayoutModel) -> None:
        self.model = model
        self.deleted_entries.clear()
        self.thumbnail_cache.clear()
        self._load_metadata_fields()
        self.refresh_list()
        self.page_list.selection_clear(0, tk.END)
        if self.model.entries:
            self.page_list.selection_set(0)
        self.status.set(f"Loaded {self.pdf_path.name}: {len(self.model.entries)} pages")
        self.refresh_preview()

    def refresh_list(self, preserve_yview: bool = False) -> None:
        if self.model is None:
            return
        yview_start = self.page_list.yview()[0] if preserve_yview else None
        self.page_list.delete(0, tk.END)
        for i, entry in enumerate(self.model.entries, start=1):
            marker = "[blank]" if entry.is_blank else "[page]"
            cover = " [cover]" if self._is_cover_entry(entry) else ""
            self.page_list.insert(tk.END, f"{i:04d} {marker}{cover} {entry.label}")
        if yview_start is not None:
            self.page_list.yview_moveto(yview_start)

    def selected_index(self) -> int | None:
        selection = self.page_list.curselection()
        return selection[0] if selection else None

    def selected_indexes(self) -> list[int]:
        return list(self.page_list.curselection())

    def insert_blank(self, before: bool) -> None:
        if self.model is None:
            return
        selected = self.selected_index()
        index = selected if selected is not None else len(self.model.entries)
        if not before:
            index += 1
        try:
            self.model.insert_blank(index)
            self.refresh_list(preserve_yview=True)
            self.page_list.selection_clear(0, tk.END)
            self.page_list.selection_set(index)
            self.refresh_preview()
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
            self.refresh_list(preserve_yview=True)
            self.page_list.selection_clear(0, tk.END)
            self.page_list.selection_set(index)
            self.refresh_preview()
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
            self.deleted_entries.append([(index, entry)])
            self.model.delete_entry(index)
            self.refresh_list(preserve_yview=True)
            if self.model.entries:
                self.page_list.selection_set(min(index, len(self.model.entries) - 1))
            self.refresh_preview()
            self.status.set(f"Removed {entry.label} from layout.")
        except Exception as exc:
            messagebox.showerror("Delete page failed", str(exc))

    def recover_last_deleted(self) -> None:
        if self.model is None or not self.deleted_entries:
            return
        group = self.deleted_entries.pop()
        restored_indexes: list[int] = []
        for original_index, entry in sorted(group, key=lambda item: item[0]):
            index = min(max(original_index, 0), len(self.model.entries))
            self.model.entries.insert(index, entry)
            restored_indexes.append(index)
        self.refresh_list(preserve_yview=True)
        self.page_list.selection_clear(0, tk.END)
        self.page_list.selection_set(restored_indexes[0])
        self.refresh_preview()
        if len(group) == 1:
            entry = group[0][1]
            self.status.set(f"Recovered {entry.label} at position {restored_indexes[0] + 1}.")
        else:
            self.status.set(f"Recovered {len(group)} pages.")

    def quick_blank_before_cover(self) -> None:
        if self.model is None:
            return
        self.model.insert_blank(0)
        self.refresh_list(preserve_yview=True)
        self.page_list.selection_clear(0, tk.END)
        self.page_list.selection_set(0)
        self.refresh_preview()
        self.status.set("Inserted one blank page before cover.")

    def quick_blank_after_cover(self) -> None:
        if self.model is None:
            return
        self.model.insert_blank(1)
        self.refresh_list(preserve_yview=True)
        self.page_list.selection_clear(0, tk.END)
        self.page_list.selection_set(1)
        self.refresh_preview()
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

    def use_current_layout_as_batch_template(self) -> None:
        if self.model is None:
            return
        self._store_metadata_fields()
        self.batch_project = BatchProject.from_template(self.model)
        self.refresh_batch_list()
        self.status.set("Batch template captured from current layout.")

    def load_batch_template_from_preset(self) -> None:
        filename = filedialog.askopenfilename(
            title="Load Batch Template Preset",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filename:
            return
        try:
            preset_path = Path(filename)
            self.batch_project = BatchProject.from_preset(preset_path)
            self.refresh_batch_list()
            self.status.set(f"Batch template loaded from preset: {preset_path.name}")
        except Exception as exc:
            messagebox.showerror("Load batch template failed", str(exc))

    def add_batch_pdfs(self) -> None:
        if self.batch_project is None:
            if self.model is None:
                return
            self.use_current_layout_as_batch_template()
        filenames = filedialog.askopenfilenames(
            title="Add PDFs to Batch",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not filenames or self.batch_project is None:
            return
        for filename in filenames:
            self.batch_project.add_pdf(Path(filename))
        self.refresh_batch_list()
        self.status.set(f"Added {len(filenames)} PDFs to batch.")

    def validate_batch(self) -> None:
        if self.batch_project is None:
            return
        output_dir = self._batch_output_dir()
        if output_dir is None:
            return
        self._run_background(
            "Batch validating...",
            lambda: self._validate_batch_work(output_dir),
            lambda _result: self._validate_batch_done(),
        )

    def _validate_batch_work(self, output_dir: Path) -> None:
        if self.batch_project is not None:
            self.batch_project.validate_all(output_dir)

    def _validate_batch_done(self) -> None:
        self.refresh_batch_list()
        self.status.set(self._batch_validation_status())

    def export_ready_batch(self) -> None:
        self._export_batch(include_warnings=False)

    def export_all_batch(self) -> None:
        self._export_batch(include_warnings=True)

    def _export_batch(self, include_warnings: bool) -> None:
        if self.batch_project is None:
            return
        output_dir = self._batch_output_dir()
        if output_dir is None:
            return
        self.batch_project.validate_all(output_dir)
        self.refresh_batch_list()
        if not self._confirm_batch_overwrites():
            self.status.set("Batch export cancelled.")
            return
        target = "all eligible items" if include_warnings else "ready items"
        self._run_background(
            f"Batch exporting {target}...",
            lambda: self.batch_project.export_all(output_dir)
            if include_warnings
            else self.batch_project.export_ready(output_dir),
            lambda summary: self._batch_project_done(summary, output_dir),
        )

    def _confirm_batch_overwrites(self) -> bool:
        if self.batch_project is None:
            return False
        existing = [
            output_path.name
            for item in self.batch_project.items
            for output_path in [getattr(item, "output_path", None)]
            if output_path is not None and output_path.exists() and item.status != "Failed"
        ]
        if not existing:
            return True
        preview = ", ".join(existing[:5])
        suffix = "" if len(existing) <= 5 else f", and {len(existing) - 5} more"
        return messagebox.askyesno("Overwrite EPUB files", f"Replace existing output files: {preview}{suffix}?")

    def refresh_batch_list(self) -> None:
        if not hasattr(self, "batch_list"):
            return
        self.batch_list.delete(0, tk.END)
        if self.batch_project is None:
            return
        for item in self.batch_project.items:
            detail = f" ({'; '.join(item.warnings)})" if item.warnings else ""
            if item.error:
                detail = f" ({item.error})"
            self.batch_list.insert(tk.END, f"{item.status} {item.pdf_path.name}{detail}")

    def _batch_output_dir(self) -> Path | None:
        initial = getattr(self, "batch_output_dir", None) or getattr(self, "output_dir", Path.cwd())
        output_dir_name = filedialog.askdirectory(title="Batch output directory", initialdir=str(initial))
        if not output_dir_name:
            return None
        self.batch_output_dir = Path(output_dir_name)
        return self.batch_output_dir

    def _batch_project_done(self, summary: dict[str, int], output_dir: Path) -> None:
        self.refresh_batch_list()
        self.status.set(
            f"Batch exported {summary['exported']} EPUB files; "
            f"{summary['failed']} failed, {summary['skipped']} skipped."
        )
        messagebox.showinfo("Batch complete", f"Exported ready EPUB files to:\n{output_dir}")

    def _batch_validation_status(self) -> str:
        if self.batch_project is None:
            return "Batch validation complete: 0 ready, 0 warning, 0 failed."
        counts = {"Ready": 0, "Warning": 0, "Failed": 0}
        for item in self.batch_project.items:
            if item.status in counts:
                counts[item.status] += 1
        return (
            "Batch validation complete: "
            f"{counts['Ready']} ready, {counts['Warning']} warning, {counts['Failed']} failed."
        )

    def normalize_export_order(self) -> None:
        if self.model is None:
            return
        self.refresh_list(preserve_yview=True)
        self.refresh_preview()
        self.status.set(f"Export will normalize {len(self.model.entries)} entries automatically.")

    def _delete_group(self, delete_action, status_message: str) -> None:
        if self.model is None:
            return
        try:
            deleted = delete_action()
            if not deleted:
                return
            if any(not entry.is_blank for _index, entry in deleted):
                labels = ", ".join(entry.label for _index, entry in deleted[:5])
                suffix = "" if len(deleted) <= 5 else f", and {len(deleted) - 5} more"
                if not messagebox.askyesno("Delete pages", f"Remove {labels}{suffix} from this export?"):
                    for original_index, entry in sorted(deleted, key=lambda item: item[0]):
                        index = min(max(original_index, 0), len(self.model.entries))
                        self.model.entries.insert(index, entry)
                    return
            self.deleted_entries.append(deleted)
            self.refresh_list(preserve_yview=True)
            self.page_list.selection_clear(0, tk.END)
            if self.model.entries:
                first_deleted = min(index for index, _entry in deleted)
                self.page_list.selection_set(min(first_deleted, len(self.model.entries) - 1))
            self.refresh_preview()
            self.status.set(_delete_status(deleted, status_message))
        except Exception as exc:
            messagebox.showerror("Delete pages failed", str(exc))

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
            self.model.apply_preset(Path(filename))
            self._load_metadata_fields()
            self.refresh_list()
            self.page_list.selection_clear(0, tk.END)
            if self.model.entries:
                self.page_list.selection_set(0)
            self.refresh_preview()
            self.status.set(f"Loaded preset: {Path(filename).name}")
        except Exception as exc:
            messagebox.showerror("Load preset failed", str(exc))

    def batch_apply_preset(self) -> None:
        preset_name = filedialog.askopenfilename(
            title="Preset to Apply",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not preset_name:
            return
        pdf_names = filedialog.askopenfilenames(
            title="PDF files to export",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialdir=str(Path.cwd()),
        )
        if not pdf_names:
            return
        output_dir_name = filedialog.askdirectory(title="Output directory", initialdir=str(Path.cwd()))
        if not output_dir_name:
            return
        preset_path = Path(preset_name)
        output_dir = Path(output_dir_name)
        self._run_background(
            "Batch exporting...",
            lambda: self._batch_apply_work(pdf_names, preset_path, output_dir),
            lambda exported: self._batch_done(len(exported), output_dir),
        )

    def _batch_apply_work(self, pdf_names, preset_path: Path, output_dir: Path) -> list[str]:
        exported = []
        for pdf_name in pdf_names:
            pdf_path = Path(pdf_name)
            model = LayoutModel.from_pdf(pdf_path)
            model.apply_preset(preset_path)
            epub_path = output_dir / pdf_path.with_suffix(".epub").name
            model.export_epub(epub_path, overwrite=True)
            exported.append(epub_path.name)
        return exported

    def _batch_done(self, count: int, output_dir: Path) -> None:
        self.status.set(f"Batch exported {count} EPUB files.")
        messagebox.showinfo("Batch complete", f"Exported {count} EPUB files to:\n{output_dir}")

    def _load_metadata_fields(self) -> None:
        if self.model is None:
            return
        self.title_var.set(self.model.title)
        self.author_var.set(self.model.author)
        self.language_var.set(self.model.language)
        self.exclude_cover_var.set(self.model.exclude_cover_from_reading)

    def _store_metadata_fields(self) -> None:
        if self.model is None:
            return
        self.model.title = self.title_var.get().strip() or self.model.source_path.stem
        self.model.author = self.author_var.get().strip()
        self.model.language = self.language_var.get().strip() or "zh-Hant"
        self.model.exclude_cover_from_reading = self.exclude_cover_var.get()

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
        if self._uses_apple_cover_gap() and selected >= 1:
            return selected + 1
        return selected

    def _spread_slots(self, pair_start: int, gap: int, page_w: int) -> list[tuple[int, int]]:
        left = (gap, gap)
        right = (gap * 2 + page_w, gap)
        if self._uses_apple_cover_gap() and pair_start == 0:
            return [left, right]
        # RTL preview: first item in regular pairs is drawn on the right.
        return [right, left]

    def _preview_entries(self):
        if self.model is None:
            return []
        entries = list(self.model.entries)
        if self._uses_apple_cover_gap():
            cover_gap = _VirtualBlank("Virtual Apple Books cover gap")
            return [entries[0], cover_gap, *entries[1:]]
        return entries

    def _uses_apple_cover_gap(self) -> bool:
        if self.model is None or not self.model.entries:
            return False
        return self.apple_preview.get()

    def _draw_entry(self, entry, x: int, y: int, max_w: int, max_h: int) -> None:
        self.preview.create_rectangle(x, y, x + max_w, y + max_h, fill="#ffffff", outline="#707070")
        if entry.is_blank:
            fill = "#a0a0a0" if isinstance(entry, _VirtualBlank) else "#606060"
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
        cache_key = (page_index, max_w, max_h)
        cached = self.thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            with fitz.open(self.pdf_path) as doc:
                page = doc[page_index - 1]
                zoom = min(max_w / page.rect.width, max_h / page.rect.height)
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                image = tk.PhotoImage(data=pix.tobytes("png"))
                self.thumbnail_cache[cache_key] = image
                return image
        except Exception:
            return None

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
        source_index = getattr(entry, "source_index", None)
        if source_index is not None:
            return ("source", source_index, max_w, max_h)
        page = getattr(entry, "page", None)
        item_id = getattr(page, "item_id", None)
        if item_id is not None:
            return ("entry", item_id, max_w, max_h)
        return ("entry", id(entry), max_w, max_h)


class _VirtualBlank:
    def __init__(self, label: str):
        self.label = label
        self.is_blank = True


def _delete_status(deleted: list[tuple[int, LayoutEntry]], fallback: str) -> str:
    if not deleted:
        return fallback
    blank_count = sum(1 for _index, entry in deleted if entry.is_blank)
    image_count = len(deleted) - blank_count
    image_word = "image" if image_count == 1 else "images"
    blank_word = "blank" if blank_count == 1 else "blanks"
    return f"Deleted {len(deleted)} entries: {image_count} {image_word}, {blank_count} {blank_word}."


def main() -> int:
    root = tk.Tk()
    EpubLayoutApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
