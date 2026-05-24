from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .layout_commands import app_commands
from .layout_support import AppCommand


class EpubLayoutCommandPaletteMixin:
    @staticmethod
    def _commands() -> tuple[AppCommand, ...]:
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
