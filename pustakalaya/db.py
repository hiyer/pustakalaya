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
    conn.execute(
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
    row = conn.execute("SELECT id FROM books WHERE path = ?", (str(path),)).fetchone()
    return row["id"]


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
    sql = f"SELECT * FROM books {where} ORDER BY title COLLATE NOCASE, id"
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


def _resolve_folder(book_path: Path, roots: list[dict]) -> str:
    """Return the immediate child folder of the matching root that contains book_path.
    Books directly in a root map to 'Uncategorized'. Books not under any root also
    map to 'Uncategorized'. Deeply nested books (e.g. root/folder/sub/book.epub)
    are attributed to the top-level folder (e.g. 'folder')."""
    for root_row in roots:
        root = Path(root_row["path"])
        try:
            rel = book_path.relative_to(root)
            return rel.parts[0] if len(rel.parts) > 1 else "Uncategorized"
        except ValueError:
            continue
    return "Uncategorized"


def get_collections(conn: sqlite3.Connection) -> list[dict]:
    """Return folder-based collections derived from book paths and library roots.
    Each entry: {name, book_count, cover_book_id}. cover_book_id is chosen
    randomly from books in the collection that have a cover. Sorted alphabetically."""
    import random

    roots = get_library_roots(conn)
    books = get_all_books(conn)

    collections: dict[str, dict] = {}
    cover_candidates: dict[str, list[int]] = {}
    for book in books:
        folder = _resolve_folder(Path(book["path"]), roots)
        if folder not in collections:
            collections[folder] = {"name": folder, "book_count": 0, "cover_book_id": None}
            cover_candidates[folder] = []
        collections[folder]["book_count"] += 1
        if book.get("cover_path"):
            cover_candidates[folder].append(book["id"])

    for folder, candidates in cover_candidates.items():
        if candidates:
            collections[folder]["cover_book_id"] = random.choice(candidates)

    return sorted(collections.values(), key=lambda c: c["name"].lower())


def get_books_in_folder(
    conn: sqlite3.Connection,
    folder_name: str,
    query: str = "",
    limit: int = 0,
    offset: int = 0,
) -> list[dict]:
    """Return books whose resolved top-level folder equals folder_name.

    Folder resolution requires Python-side path matching against library roots,
    so filtering and pagination are applied in Python after fetching all
    query-matching books from the database. limit/offset are relative to
    the folder's book list, not the overall library.
    """
    roots = get_library_roots(conn)
    all_books = get_all_books(conn, query=query)
    result = [
        b for b in all_books
        if _resolve_folder(Path(b["path"]), roots) == folder_name
    ]
    if limit > 0:
        result = result[offset : offset + limit]
    return result
