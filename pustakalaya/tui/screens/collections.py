# pustakalaya/tui/screens/collections.py
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Header

from pustakalaya import db
from pustakalaya.tui.screens.main import BooksPane


class CollectionsPane(Widget):
    DEFAULT_CSS = """
    CollectionsPane { height: 1fr; }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._collections: list[dict] = []

    def compose(self) -> ComposeResult:
        yield DataTable(id="col-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Folder", "Books")
        self._load_collections()

    def _load_collections(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self._collections = db.get_collections(self.app.conn)
        for col in self._collections:
            table.add_row(col["name"], str(col["book_count"]))

    def refresh_collections(self) -> None:
        self._load_collections()

    def selected_collection(self) -> dict | None:
        table = self.query_one(DataTable)
        if table.cursor_row < 0 or not self._collections:
            return None
        try:
            return self._collections[table.cursor_row]
        except IndexError:
            return None

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        col = self.selected_collection()
        if col is not None:
            self.app.push_screen(CollectionBooksScreen(col["name"]))


class CollectionBooksScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("o", "open_book", "Open", show=True),
        Binding("e", "edit_metadata", "Edit", show=True),
    ]

    def __init__(self, folder_name: str):
        super().__init__()
        self.folder_name = folder_name

    def compose(self) -> ComposeResult:
        yield Header()
        yield BooksPane(folder_filter=self.folder_name, id="col-books-pane")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = self.folder_name

    def action_open_book(self) -> None:
        import subprocess

        books_pane = self.query_one(BooksPane)
        book = books_pane.selected_book()
        if book is None:
            self.app.notify("No book selected", severity="warning")
            return
        try:
            subprocess.Popen(["xdg-open", book["path"]], start_new_session=True)
        except Exception as e:
            self.app.notify(str(e), severity="error")

    def action_edit_metadata(self) -> None:
        books_pane = self.query_one(BooksPane)
        book = books_pane.selected_book()
        if book is None:
            self.app.notify("No book selected", severity="warning")
            return
        from pustakalaya.tui.screens.metadata import MetadataModal

        self.app.push_screen(MetadataModal(book, books_pane=books_pane))
