# pustakalaya/tui/app.py
from __future__ import annotations

import sqlite3
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane
from textual.worker import Worker

from pustakalaya.tui.screens.collections import CollectionsPane
from pustakalaya.tui.screens.main import BooksPane
from pustakalaya.tui.screens.roots import RootsPane


class PustakalayaApp(App):
    TITLE = "pustakalaya"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("o", "open_book", "Open", show=True),
        Binding("e", "edit_metadata", "Edit", show=True),
        Binding("s", "scan_all", "Scan", show=True),
        Binding("/", "focus_search", "Search", show=True),
        Binding("1", "tab_collections", "Collections", show=True),
        Binding("2", "tab_books", "Books", show=True),
        Binding("3", "tab_roots", "Roots", show=True),
    ]

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        covers_dir: Path | None = None,
    ):
        super().__init__()
        data_dir = Path.home() / ".local" / "share" / "pustakalaya"
        if conn is None:
            from pustakalaya import db

            conn = db.init(data_dir / "library.db")
        self.conn = conn
        self.covers_dir = covers_dir or (data_dir / "covers")
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self._watcher: "LibraryWatcher | None" = None

    def on_mount(self) -> None:
        from pustakalaya import db
        from pustakalaya.watcher import LibraryWatcher

        self._watcher = LibraryWatcher(self.conn, self.covers_dir)
        for root in db.get_library_roots(self.conn):
            self._watcher.add_root(Path(root["path"]))
        self._watcher.start()

    def on_unmount(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Collections", id="tab-collections"):
                yield CollectionsPane()
            with TabPane("All Books", id="tab-books"):
                yield BooksPane()
            with TabPane("Library Roots", id="tab-roots"):
                yield RootsPane()
        yield Footer()

    def action_tab_collections(self) -> None:
        self.query_one(TabbedContent).active = "tab-collections"

    def action_tab_books(self) -> None:
        self.query_one(TabbedContent).active = "tab-books"

    def action_tab_roots(self) -> None:
        self.query_one(TabbedContent).active = "tab-roots"

    def action_open_book(self) -> None:
        import subprocess

        books_pane = self.query_one("#tab-books BooksPane", BooksPane)
        book = books_pane.selected_book()
        if book is None:
            self.notify("No book selected", severity="warning")
            return
        try:
            subprocess.Popen(["xdg-open", book["path"]], start_new_session=True)
        except Exception as e:
            self.notify(str(e), severity="error")

    def action_edit_metadata(self) -> None:
        books_pane = self.query_one("#tab-books BooksPane", BooksPane)
        book = books_pane.selected_book()
        if book is None:
            self.notify("No book selected", severity="warning")
            return
        from pustakalaya.tui.screens.metadata import MetadataModal

        self.push_screen(MetadataModal(book, books_pane=books_pane))

    def action_scan_all(self) -> None:
        self.notify("Scanning…")
        self.run_worker(self._do_scan, thread=True, exclusive=True, name="scan")

    def _do_scan(self) -> None:
        from pustakalaya.scanner import scan_all

        scan_all(self.conn, self.covers_dir)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        from textual.worker import WorkerState

        if event.worker.name != "scan":
            return
        if event.state == WorkerState.SUCCESS:
            self.query_one("#tab-books BooksPane", BooksPane).refresh_books()
            self.query_one(CollectionsPane).refresh_collections()
            self.notify("Scan complete")
        elif event.state in (WorkerState.ERROR, WorkerState.CANCELLED):
            err = str(event.worker.error) if event.worker.error else "Scan failed"
            self.notify(err, severity="error")

    def action_focus_search(self) -> None:
        from textual.css.query import NoMatches
        from textual.widgets import Input

        try:
            self.query_one("#search-input", Input).focus()
        except NoMatches:
            pass


def main() -> None:
    import textual_image.renderable  # must be imported before app.run() to detect terminal

    PustakalayaApp().run()
