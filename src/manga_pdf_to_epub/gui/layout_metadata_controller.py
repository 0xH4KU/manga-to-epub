from __future__ import annotations

from .layout_support import PlainTextVariable


class EpubLayoutMetadataMixin:
    @staticmethod
    def _metadata_label_texts(series_mode: bool) -> tuple[str, str]:
        if series_mode:
            return ("Series Title", "Series Author")
        return ("Title", "Author")

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
        model = getattr(self, "model", None)
        series_project = getattr(self, "series_project", None)
        if model is None and series_project is None:
            return
        title_var = getattr(self, "title_var", None)
        author_var = getattr(self, "author_var", None)
        language_var = getattr(self, "language_var", None)
        if title_var is None or author_var is None or language_var is None:
            return
        title = title_var.get().strip()
        author = author_var.get().strip()
        language = language_var.get().strip() or "zh-Hant"
        if series_project is not None:
            series_project.title = title or series_project.title
            series_project.author = author
            series_project.language = language
            if model is None:
                return
            active_volume = getattr(self, "active_series_volume", None)
            if active_volume is not None and hasattr(series_project, "generated_title"):
                model.title = series_project.generated_title(active_volume)
            model.author = series_project.author
            model.language = series_project.language
        else:
            model.title = title or model.source_path.stem
            model.author = author
            model.language = language
        exclude_cover_var = getattr(self, "exclude_cover_var", None)
        if exclude_cover_var is not None:
            model.exclude_cover_from_reading = exclude_cover_var.get()

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
