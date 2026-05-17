#!/usr/bin/env python3
"""Small GUI for tuning EPUB blank-page placement before export."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import fitz

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
        self.deleted_entries: list[tuple[int, LayoutEntry]] = []
        self.status = tk.StringVar(value="Open a PDF to begin.")
        self.apple_preview = tk.BooleanVar(value=True)

        self._build_ui()
        self.root.bind_all("<Command-z>", lambda _event: self.recover_last_deleted())
        self.root.bind_all("<Control-z>", lambda _event: self.recover_last_deleted())

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
        self.page_list = tk.Listbox(left, exportselection=False, activestyle="dotbox")
        self.page_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.page_list.bind("<<ListboxSelect>>", lambda _event: self.refresh_preview())

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
        ttk.Label(right, text="Blank pages").pack(anchor=tk.W)
        ttk.Button(right, text="Insert Blank Before", command=lambda: self.insert_blank(before=True)).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Insert Blank After", command=lambda: self.insert_blank(before=False)).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Delete Selected Page", command=self.delete_selected_entry).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Recover Last Deleted", command=self.recover_last_deleted).pack(fill=tk.X, pady=(8, 0))
        ttk.Separator(right).pack(fill=tk.X, pady=16)
        ttk.Button(right, text="Quick: Blank Before Cover", command=self.quick_blank_before_cover).pack(fill=tk.X)
        ttk.Button(right, text="Quick: Blank After Cover", command=self.quick_blank_after_cover).pack(fill=tk.X, pady=(8, 0))
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
        self.status.set("Loading PDF images...")
        self.root.update_idletasks()
        try:
            self.model = LayoutModel.from_pdf(self.pdf_path)
            self.deleted_entries.clear()
            self.thumbnail_cache.clear()
            self.refresh_list()
            self.page_list.selection_clear(0, tk.END)
            if self.model.entries:
                self.page_list.selection_set(0)
            self.status.set(f"Loaded {self.pdf_path.name}: {len(self.model.entries)} pages")
            self.refresh_preview()
        except Exception as exc:
            messagebox.showerror("Open PDF failed", str(exc))
            self.status.set("Open PDF failed.")

    def refresh_list(self, preserve_yview: bool = False) -> None:
        if self.model is None:
            return
        yview_start = self.page_list.yview()[0] if preserve_yview else None
        self.page_list.delete(0, tk.END)
        for i, entry in enumerate(self.model.entries, start=1):
            marker = "[blank]" if entry.is_blank else "[page]"
            self.page_list.insert(tk.END, f"{i:04d} {marker} {entry.label}")
        if yview_start is not None:
            self.page_list.yview_moveto(yview_start)

    def selected_index(self) -> int | None:
        selection = self.page_list.curselection()
        return selection[0] if selection else None

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
            self.deleted_entries.append((index, entry))
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
        original_index, entry = self.deleted_entries.pop()
        index = min(max(original_index, 0), len(self.model.entries))
        self.model.entries.insert(index, entry)
        self.refresh_list(preserve_yview=True)
        self.page_list.selection_clear(0, tk.END)
        self.page_list.selection_set(index)
        self.refresh_preview()
        self.status.set(f"Recovered {entry.label} at position {index + 1}.")

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

    def export_epub(self) -> None:
        if self.model is None or self.pdf_path is None:
            return
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
        self.status.set("Exporting EPUB...")
        self.root.update_idletasks()

        def worker() -> None:
            try:
                counts = self.model.export_epub(epub_path, overwrite=True)
                self.root.after(0, lambda: self._export_done(epub_path, counts))
            except Exception as exc:
                self.root.after(0, lambda: self._export_failed(exc))

        threading.Thread(target=worker, daemon=True).start()

    def save_preset(self) -> None:
        if self.model is None:
            return
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
        self.status.set("Batch exporting...")
        self.root.update_idletasks()

        def worker() -> None:
            try:
                exported = []
                for pdf_name in pdf_names:
                    pdf_path = Path(pdf_name)
                    model = LayoutModel.from_pdf(pdf_path)
                    model.apply_preset(preset_path)
                    epub_path = output_dir / pdf_path.with_suffix(".epub").name
                    model.export_epub(epub_path, overwrite=True)
                    exported.append(epub_path.name)
                self.root.after(0, lambda: self._batch_done(len(exported), output_dir))
            except Exception as exc:
                self.root.after(0, lambda: self._export_failed(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _batch_done(self, count: int, output_dir: Path) -> None:
        self.status.set(f"Batch exported {count} EPUB files.")
        messagebox.showinfo("Batch complete", f"Exported {count} EPUB files to:\n{output_dir}")

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


class _VirtualBlank:
    def __init__(self, label: str):
        self.label = label
        self.is_blank = True


def main() -> int:
    root = tk.Tk()
    EpubLayoutApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
