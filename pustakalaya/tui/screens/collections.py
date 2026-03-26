# pustakalaya/tui/screens/collections.py
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Header, Label
from textual_image.widget import Image as CoverImage

from pustakalaya import db
from pustakalaya.tui.screens.main import BooksPane


class CollectionCover(Widget):
    DEFAULT_CSS = """
    CollectionCover {
        width: 30;
        border: solid $primary;
        padding: 1;
        align: center top;
    }
    CollectionCover .cover-img {
        width: auto;
        height: 12;
    }
    CollectionCover #cover-name {
        text-style: bold;
        width: 100%;
        text-align: center;
    }
    CollectionCover #cover-count {
        width: 100%;
        text-align: center;
    }
    """

    def compose(self) -> ComposeResult:
        yield CoverImage(classes="cover-img")
        yield Label("", id="cover-name")
        yield Label("", id="cover-count")

    def show(self, collection: dict | None) -> None:
        cover_img = self.query_one(".cover-img", CoverImage)
        if collection is None:
            cover_img.image = None
            self.query_one("#cover-name", Label).update("")
            self.query_one("#cover-count", Label).update("")
            return
        cover_book_id = collection.get("cover_book_id")
        if cover_book_id:
            cover_file = self.app.covers_dir / f"{cover_book_id}.jpg"
            cover_img.image = str(cover_file) if cover_file.exists() else None
        else:
            cover_img.image = None
        self.query_one("#cover-name", Label).update(collection["name"])
        count = collection["book_count"]
        self.query_one("#cover-count", Label).update(
            f"{count} book{'s' if count != 1 else ''}"
        )


class CollectionsPane(Widget):
    DEFAULT_CSS = """
    CollectionsPane { height: 1fr; }
    CollectionsPane > Horizontal { height: 1fr; }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._collections: list[dict] = []

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield CollectionCover()
            yield DataTable(id="col-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Folder", "Books")
        self._load_collections()

    def on_show(self) -> None:
        self.query_one(DataTable).focus()

    def _load_collections(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self._collections = db.get_collections(self.app.conn)
        for col in self._collections:
            table.add_row(col["name"], str(col["book_count"]))
        if self._collections:
            table.move_cursor(row=0)
            self.query_one(CollectionCover).show(self._collections[0])

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

    @on(DataTable.RowHighlighted)
    def _on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row = event.cursor_row
        col = self._collections[row] if 0 <= row < len(self._collections) else None
        self.query_one(CollectionCover).show(col)

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        col = self.selected_collection()
        if col is not None:
            self.app.push_screen(CollectionBooksScreen(col["name"]))


class CollectionBooksScreen(Screen):
    DEFAULT_CSS = """
    CollectionBooksScreen #book-detail { display: none; }
    """
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("o", "open_book", "Open", show=True),
        Binding("e", "edit_metadata", "Edit", show=True),
        Binding("1", "nav_collections", "Collections", show=False),
        Binding("2", "nav_books", "Books", show=False),
        Binding("3", "nav_roots", "Roots", show=False),
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

    def _pop(self) -> None:
        self.app.pop_screen()
        try:
            cover_img = self.app.query_one(CollectionsPane).query_one(
                ".cover-img", CoverImage
            )
            saved = cover_img.image
            # Two-frame repaint: textual_image writes outside Textual's render model,
            # so the differential renderer won't repaint cells it thinks are unchanged.
            # Frame 1 (image=None): Textual writes empty cells + sends Kitty delete,
            # clearing the ghost text left by the DataTable in the popped screen.
            # Frame 2 (call_after_refresh): image is restored on the clean text layer.
            cover_img.image = None
            cover_img.call_after_refresh(lambda: setattr(cover_img, "image", saved))
        except Exception:
            pass

    def action_back(self) -> None:
        self._pop()

    def action_nav_collections(self) -> None:
        self._pop()

    def action_nav_books(self) -> None:
        self._pop()
        self.app.action_tab_books()

    def action_nav_roots(self) -> None:
        self._pop()
        self.app.action_tab_roots()

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
