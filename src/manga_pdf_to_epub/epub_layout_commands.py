from __future__ import annotations

from .epub_layout_gui_support import AppCommand


def app_commands() -> tuple[AppCommand, ...]:
    return (
        AppCommand("Open PDF", "open_pdf", keywords=("import", "load")),
        AppCommand("Import Series", "import_series", keywords=("folder", "volumes")),
        AppCommand("Export EPUB", "export_epub", keywords=("save",)),
        AppCommand("Mark Selected Volume Ready", "mark_selected_series_volume_ready", keywords=("series",)),
        AppCommand("Unready Selected", "unready_selected", keywords=("series", "undo")),
        AppCommand("Export Ready Series", "export_ready_series", keywords=("series",)),
        AppCommand("Validate Series", "validate_series", keywords=("series", "check")),
        AppCommand("Save Project", "save_project", keywords=("series", "project")),
        AppCommand("Open Project", "open_project", keywords=("series", "project")),
        AppCommand("Save Preset", "save_preset", keywords=("layout",)),
        AppCommand("Load Preset", "load_preset", keywords=("layout",)),
        AppCommand("Insert Blank Before", "insert_blank", (True,), ("page",)),
        AppCommand("Insert Blank After", "insert_blank", (False,), ("page",)),
        AppCommand("Insert Image Before", "insert_image", (True,), ("page",)),
        AppCommand("Insert Image After", "insert_image", (False,), ("page",)),
        AppCommand("Delete Selected Page", "delete_selected_entry", keywords=("remove",)),
        AppCommand("Delete First...", "ask_delete_first", keywords=("bulk", "remove")),
        AppCommand("Delete Last...", "ask_delete_last", keywords=("bulk", "remove")),
        AppCommand("Delete Range...", "ask_delete_range", keywords=("bulk", "remove")),
        AppCommand("Recover Last Deleted", "recover_last_deleted", keywords=("undo",)),
        AppCommand("Set Selected As Cover", "set_selected_as_cover", keywords=("metadata",)),
        AppCommand("Export Selected Images", "export_selected_images", keywords=("extract",)),
    )
