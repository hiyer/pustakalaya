# pustakalaya/watcher.py
import sqlite3
from pathlib import Path

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from pustakalaya import db
from pustakalaya.scanner import SUPPORTED_EXTENSIONS, scan_file


class LibraryEventHandler(FileSystemEventHandler):
    def __init__(self, conn: sqlite3.Connection, covers_dir: Path):
        super().__init__()
        self.conn = conn
        self.covers_dir = covers_dir

    def on_created_or_moved_to(self, path: Path) -> None:
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        if not path.is_file():
            return
        try:
            scan_file(self.conn, path, self.covers_dir)
        except Exception:
            pass

    def on_deleted_or_moved_from(self, path: Path) -> None:
        db.delete_book(self.conn, path)

    # watchdog callbacks
    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self.on_created_or_moved_to(Path(event.src_path))

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if not event.is_directory:
            self.on_deleted_or_moved_from(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:
        if not event.is_directory:
            self.on_deleted_or_moved_from(Path(event.src_path))
            self.on_created_or_moved_to(Path(event.dest_path))


class LibraryWatcher:
    """Wraps watchdog Observer; manages per-root watches."""

    def __init__(self, conn: sqlite3.Connection, covers_dir: Path):
        self.conn = conn
        self.covers_dir = covers_dir
        self._observer = Observer()
        self._handler = LibraryEventHandler(conn, covers_dir)
        self._watches: dict[str, object] = {}  # path → Watch

    def start(self) -> None:
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()

    def add_root(self, path: Path) -> None:
        key = str(path)
        if key not in self._watches and path.is_dir():
            watch = self._observer.schedule(self._handler, str(path), recursive=True)
            self._watches[key] = watch

    def remove_root(self, path: Path) -> None:
        key = str(path)
        if key in self._watches:
            self._observer.unschedule(self._watches.pop(key))
