import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    title       TEXT,
    author      TEXT,
    publisher   TEXT,
    year        INTEGER,
    format      TEXT NOT NULL,
    cover_path  TEXT,
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS books_updated_at
AFTER UPDATE OF title, author, publisher, year, format, cover_path, path ON books
FOR EACH ROW
BEGIN
    UPDATE books SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TABLE IF NOT EXISTS library_roots (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def init(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the database, set WAL mode, apply schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_book(conn: sqlite3.Connection, path: Path, meta: dict) -> int:
    """Insert or replace a book record. Returns the book id."""
    cursor = conn.execute(
        """
        INSERT INTO books (path, title, author, publisher, year, format, cover_path)
        VALUES (:path, :title, :author, :publisher, :year, :format, :cover_path)
        ON CONFLICT(path) DO UPDATE SET
            title      = excluded.title,
            author     = excluded.author,
            publisher  = excluded.publisher,
            year       = excluded.year,
            format     = excluded.format,
            cover_path = excluded.cover_path
        """,
        {
            "path": str(path),
            "title": meta.get("title"),
            "author": meta.get("author"),
            "publisher": meta.get("publisher"),
            "year": meta.get("year"),
            "format": meta["format"],
            "cover_path": meta.get("cover_path"),
        },
    )
    conn.commit()
    return cursor.lastrowid


def update_cover(conn: sqlite3.Connection, book_id: int, cover_path: str) -> None:
    conn.execute("UPDATE books SET cover_path = ? WHERE id = ?", (cover_path, book_id))
    conn.commit()


def delete_book(conn: sqlite3.Connection, path: Path) -> bool:
    """Delete a book by path. Returns True if a row was deleted, False if not found."""
    cursor = conn.execute("DELETE FROM books WHERE path = ?", (str(path),))
    conn.commit()
    return cursor.rowcount > 0


def get_book(conn: sqlite3.Connection, book_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    return dict(row) if row else None


def get_book_by_path(conn: sqlite3.Connection, path: Path) -> dict | None:
    row = conn.execute("SELECT * FROM books WHERE path = ?", (str(path),)).fetchone()
    return dict(row) if row else None


def get_all_books(
    conn: sqlite3.Connection,
    query: str = "",
    limit: int = 0,
    offset: int = 0,
) -> list[dict]:
    """Return books, optionally filtered by title/author substring (case-insensitive).
    limit=0 means no limit."""
    if query:
        like = f"%{query}%"
        where = "WHERE title LIKE :like OR author LIKE :like"
        params: dict = {"like": like}
    else:
        where = ""
        params = {}
    sql = f"SELECT * FROM books {where} ORDER BY title COLLATE NOCASE"
    if limit > 0:
        sql += " LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def add_library_root(conn: sqlite3.Connection, path: Path) -> None:
    conn.execute("INSERT OR IGNORE INTO library_roots (path) VALUES (?)", (str(path),))
    conn.commit()


def remove_library_root(conn: sqlite3.Connection, path: Path) -> None:
    conn.execute("DELETE FROM library_roots WHERE path = ?", (str(path),))
    conn.commit()


def get_library_roots(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM library_roots ORDER BY path").fetchall()
    return [dict(r) for r in rows]
