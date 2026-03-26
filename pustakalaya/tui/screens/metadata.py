# pustakalaya/tui/screens/metadata.py
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label
from textual.containers import Vertical


class MetadataModal(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "Cancel"),
    ]
    DEFAULT_CSS = """
    MetadataModal {
        align: center middle;
    }
    #modal-box {
        width: 60;
        border: thick $primary;
        padding: 1 2;
        background: $surface;
    }
    """

    def __init__(self, book: dict, books_pane=None):
        super().__init__()
        self.book = book
        self._books_pane = books_pane

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Label(f"Edit: {self.book.get('title') or self.book['path']}")
            yield Label("Title:")
            yield Input(value=self.book.get("title") or "", id="f-title")
            yield Label("Author:")
            yield Input(value=self.book.get("author") or "", id="f-author")
            yield Label("Publisher:")
            yield Input(value=self.book.get("publisher") or "", id="f-publisher")
            yield Label("Year:")
            yield Input(value=str(self.book.get("year") or ""), id="f-year")
            yield Button("Save", id="btn-save", variant="primary")
            yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
            return
        if event.button.id == "btn-save":
            self._save()

    def _save(self) -> None:
        from pustakalaya import db

        def val(fid):
            return self.query_one(f"#{fid}", Input).value.strip() or None

        year_str = val("f-year")
        try:
            year = int(year_str) if year_str else None
        except ValueError:
            self.app.notify("Year must be a number", severity="error")
            return

        try:
            from pathlib import Path

            db.upsert_book(
                self.app.conn,
                Path(self.book["path"]),
                {
                    "title": val("f-title"),
                    "author": val("f-author"),
                    "publisher": val("f-publisher"),
                    "year": year,
                    "format": self.book["format"],
                    "cover_path": self.book.get("cover_path"),
                },
            )
            # Refresh the originating pane, or fall back to the tab-books pane
            if self._books_pane is not None:
                self._books_pane.refresh_books()
            else:
                from pustakalaya.tui.screens.main import BooksPane
                self.app.query_one("#tab-books BooksPane", BooksPane).refresh_books()
            self.dismiss(True)
        except Exception as e:
            self.app.notify(str(e), severity="error")
