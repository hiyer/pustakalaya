# pustakalaya/tui/screens/main.py
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.widgets import DataTable, Input, Label, Static
from textual.widget import Widget
from textual.containers import Horizontal, Vertical
from textual_image.widget import Image as CoverImage

from pustakalaya import db


class BookDetail(Static):
    DEFAULT_CSS = """
    BookDetail {
        width: 35;
        border: solid $primary;
        padding: 1;
    }
    #detail-cover { width: auto; height: 12; }
    """

    def compose(self) -> ComposeResult:
        yield CoverImage(id="detail-cover")
        yield Label("(no book selected)", id="detail-title")
        yield Label("", id="detail-author")
        yield Label("", id="detail-year")
        yield Label("", id="detail-format")
        yield Label("", id="detail-path")

    def show(self, book: dict | None) -> None:
        cover = self.query_one("#detail-cover", CoverImage)
        if book is None:
            cover.image = None
            self.query_one("#detail-title", Label).update("(no book selected)")
            for fid in ("#detail-author", "#detail-year", "#detail-format", "#detail-path"):
                self.query_one(fid, Label).update("")
            return
        cover_path = book.get("cover_path")
        cover.image = cover_path if cover_path else None
        self.query_one("#detail-title", Label).update(book.get("title") or "")
        self.query_one("#detail-author", Label).update(f"Author: {book.get('author') or '—'}")
        self.query_one("#detail-year", Label).update(f"Year:   {book.get('year') or '—'}")
        self.query_one("#detail-format", Label).update(f"Format: {book.get('format', '')}")
        self.query_one("#detail-path", Label).update(f"Path: {book.get('path', '')}")


class BooksPane(Widget):
    DEFAULT_CSS = """
    BooksPane { height: 1fr; }
    """

    def __init__(self, *args, folder_filter: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.folder_filter = folder_filter
        self._books: list[dict] = []
        self._search_timer = None

    def compose(self) -> ComposeResult:
        if self.folder_filter is None:
            yield Input(placeholder="/ to search...", id="search-input")
        with Horizontal():
            yield DataTable(id="book-table", cursor_type="row")
            yield BookDetail(id="book-detail")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Title", "Author", "Format")
        self._load_books()

    def _load_books(self, query: str = "") -> None:
        table = self.query_one(DataTable)
        table.clear()
        if self.folder_filter is not None:
            self._books = db.get_books_in_folder(self.app.conn, self.folder_filter)
        else:
            self._books = db.get_all_books(self.app.conn, query=query)
        for book in self._books:
            table.add_row(
                book.get("title") or "",
                book.get("author") or "",
                book.get("format") or "",
                key=str(book["id"]),
            )

    def refresh_books(self, query: str = "") -> None:
        self._load_books(query)

    def selected_book(self) -> dict | None:
        table = self.query_one(DataTable)
        if table.cursor_row < 0 or not self._books:
            return None
        try:
            return self._books[table.cursor_row]
        except IndexError:
            return None

    @on(DataTable.RowHighlighted)
    def _on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        book = self.selected_book()
        self.query_one(BookDetail).show(book)

    @on(Input.Changed, "#search-input")
    def _on_search_changed(self, event: Input.Changed) -> None:
        if self._search_timer is not None:
            self._search_timer.stop()
        self._search_timer = self.set_timer(0.3, lambda: self._load_books(event.value))

    @on(Input.Submitted, "#search-input")
    def _on_search_submitted(self, event: Input.Submitted) -> None:
        self.query_one(DataTable).focus()

    def on_key(self, event) -> None:
        if self.folder_filter is not None:
            return
        if event.key == "escape" and self.query_one("#search-input", Input).has_focus:
            self.query_one("#search-input", Input).value = ""
            self.query_one(DataTable).focus()
