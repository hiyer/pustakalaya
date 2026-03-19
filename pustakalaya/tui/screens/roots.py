# pustakalaya/tui/screens/roots.py
from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Button, Input, Label, ListView, ListItem

from pustakalaya import db


class RootsPane(Widget):
    DEFAULT_CSS = """
    RootsPane { padding: 1; height: auto; }
    #roots-list { height: 10; border: solid $primary; }
    #add-row { margin-top: 1; layout: horizontal; height: auto; }
    #path-input { width: 1fr; }
    """

    def compose(self) -> ComposeResult:
        yield Label("Watched directories:")
        yield ListView(id="roots-list")
        with Widget(id="add-row"):
            yield Input(placeholder="Directory path...", id="path-input")
            yield Button("Add", id="btn-add", variant="primary")
            yield Button("Remove selected", id="btn-remove", variant="error")

    def on_mount(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        lv = self.query_one(ListView)
        lv.clear()
        for root in db.get_library_roots(self.app.conn):
            lv.append(ListItem(Label(root["path"])))

    @on(Button.Pressed, "#btn-add")
    def _add_root(self) -> None:
        inp = self.query_one("#path-input", Input)
        path = Path(inp.value.strip())
        if not path.is_dir():
            self.app.notify(f"Not a directory: {path}", severity="error")
            return
        db.add_library_root(self.app.conn, path)
        if self.app._watcher is not None:
            self.app._watcher.add_root(path)
        inp.value = ""
        self._refresh_list()

    @on(Button.Pressed, "#btn-remove")
    def _remove_root(self) -> None:
        lv = self.query_one(ListView)
        item = lv.highlighted_child
        if item is None:
            return
        path = Path(item.query_one(Label).renderable)
        db.remove_library_root(self.app.conn, path)
        if self.app._watcher is not None:
            self.app._watcher.remove_root(path)
        self._refresh_list()
