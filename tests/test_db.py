import sqlite3
from pathlib import Path
import pytest
from pustakalaya import db


def test_init_creates_tables(tmp_path):
    conn = db.init(tmp_path / "library.db")
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"books", "library_roots"} <= tables


def test_init_sets_wal_mode(tmp_path):
    conn = db.init(tmp_path / "library.db")
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"


def test_upsert_book_insert(tmp_path):
    conn = db.init(tmp_path / "library.db")
    book_id = db.upsert_book(
        conn,
        Path("/books/dune.epub"),
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "publisher": "Chilton",
            "year": 1965,
            "format": "epub",
            "cover_path": None,
        },
    )
    assert isinstance(book_id, int)
    book = db.get_book(conn, book_id)
    assert book["title"] == "Dune"
    assert book["author"] == "Frank Herbert"
    assert book["year"] == 1965


def test_upsert_book_overwrites(tmp_path):
    conn = db.init(tmp_path / "library.db")
    path = Path("/books/dune.epub")
    id1 = db.upsert_book(
        conn,
        path,
        {
            "title": "Dun",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    id2 = db.upsert_book(
        conn,
        path,
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "publisher": None,
            "year": 1965,
            "format": "epub",
            "cover_path": None,
        },
    )
    assert id1 == id2, "upsert must return same id for existing row"
    books = db.get_all_books(conn)
    assert len(books) == 1
    assert books[0]["title"] == "Dune"


def test_delete_book(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.upsert_book(
        conn,
        Path("/books/dune.epub"),
        {
            "title": "Dune",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    deleted = db.delete_book(conn, Path("/books/dune.epub"))
    assert deleted is True
    assert db.get_all_books(conn) == []
    not_found = db.delete_book(conn, Path("/books/dune.epub"))
    assert not_found is False


def test_get_all_books_null_fields(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.upsert_book(
        conn,
        Path("/mystery.epub"),
        {
            "title": None,
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    books = db.get_all_books(conn)
    assert len(books) == 1


def test_get_all_books_search(tmp_path):
    conn = db.init(tmp_path / "library.db")
    for path, title, author in [
        ("/a.epub", "Dune", "Frank Herbert"),
        ("/b.pdf", "Neuromancer", "William Gibson"),
    ]:
        db.upsert_book(
            conn,
            Path(path),
            {
                "title": title,
                "author": author,
                "publisher": None,
                "year": None,
                "format": "epub",
                "cover_path": None,
            },
        )
    assert len(db.get_all_books(conn, query="dune")) == 1
    assert len(db.get_all_books(conn, query="GIBSON")) == 1
    assert len(db.get_all_books(conn, query="")) == 2


def test_update_cover(tmp_path):
    conn = db.init(tmp_path / "library.db")
    book_id = db.upsert_book(
        conn,
        Path("/books/dune.epub"),
        {
            "title": "Dune",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    db.update_cover(conn, book_id, "/covers/1.jpg")
    assert db.get_book(conn, book_id)["cover_path"] == "/covers/1.jpg"


def test_library_roots(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, Path("/books"))
    db.add_library_root(conn, Path("/comics"))
    roots = db.get_library_roots(conn)
    assert len(roots) == 2
    assert any(r["path"] == "/books" for r in roots)
    db.remove_library_root(conn, Path("/books"))
    assert len(db.get_library_roots(conn)) == 1


def test_get_all_books_pagination(tmp_path):
    conn = db.init(tmp_path / "library.db")
    for i in range(5):
        db.upsert_book(
            conn,
            Path(f"/{i}.epub"),
            {
                "title": f"Book {i}",
                "author": None,
                "publisher": None,
                "year": None,
                "format": "epub",
                "cover_path": None,
            },
        )
    page1 = db.get_all_books(conn, limit=3, offset=0)
    page2 = db.get_all_books(conn, limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 2


def test_upsert_book_stable_id_after_other_inserts(tmp_path):
    """upsert returns the existing row's id even when other rows were inserted after it."""
    conn = db.init(tmp_path / "library.db")
    id_a = db.upsert_book(
        conn,
        Path("/a.epub"),
        {
            "title": "A",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    db.upsert_book(
        conn,
        Path("/b.epub"),
        {
            "title": "B",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    # Re-upsert /a — must return id_a, not /b's id
    id_a2 = db.upsert_book(
        conn,
        Path("/a.epub"),
        {
            "title": "A updated",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    assert id_a == id_a2


def test_get_collections_basic(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    # Book in subfolder
    db.upsert_book(
        conn,
        tmp_path / "books" / "junji-ito" / "uzumaki.cbz",
        {
            "title": "Uzumaki",
            "author": "Junji Ito",
            "publisher": None,
            "year": None,
            "format": "cbz",
            "cover_path": None,
        },
    )
    # Book directly in root → Uncategorized
    db.upsert_book(
        conn,
        tmp_path / "books" / "standalone.epub",
        {
            "title": "Standalone",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    colls = db.get_collections(conn)
    names = [c["name"] for c in colls]
    assert "junji-ito" in names
    assert "Uncategorized" in names
    jito = next(c for c in colls if c["name"] == "junji-ito")
    assert jito["book_count"] == 1
    uncategorized = next(c for c in colls if c["name"] == "Uncategorized")
    assert uncategorized["book_count"] == 1


def test_get_collections_cover_book_id(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    book_id = db.upsert_book(
        conn,
        tmp_path / "books" / "junji-ito" / "uzumaki.cbz",
        {
            "title": "Uzumaki",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "cbz",
            "cover_path": None,
        },
    )
    # No covers yet
    colls = db.get_collections(conn)
    jito = next(c for c in colls if c["name"] == "junji-ito")
    assert jito["cover_book_id"] is None

    # Add a cover
    db.update_cover(conn, book_id, str(tmp_path / "covers" / "1.jpg"))
    colls2 = db.get_collections(conn)
    jito2 = next(c for c in colls2 if c["name"] == "junji-ito")
    assert jito2["cover_book_id"] == book_id


def test_get_collections_cover_book_id_random(tmp_path):
    """cover_book_id is one of the books with a cover (random selection)."""
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    ids = []
    for title in ["Uzumaki", "Gyo", "Tomie"]:
        bid = db.upsert_book(
            conn,
            tmp_path / "books" / "junji-ito" / f"{title}.cbz",
            {
                "title": title,
                "author": None,
                "publisher": None,
                "year": None,
                "format": "cbz",
                "cover_path": None,
            },
        )
        db.update_cover(conn, bid, str(tmp_path / "covers" / f"{bid}.jpg"))
        ids.append(bid)
    colls = db.get_collections(conn)
    jito = next(c for c in colls if c["name"] == "junji-ito")
    assert jito["cover_book_id"] in ids


def test_get_collections_orphaned_book_goes_to_uncategorized(tmp_path):
    conn = db.init(tmp_path / "library.db")
    # No library root registered; book path won't match anything
    db.upsert_book(
        conn,
        tmp_path / "orphan.epub",
        {
            "title": "Orphan",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    colls = db.get_collections(conn)
    assert len(colls) == 1
    assert colls[0]["name"] == "Uncategorized"


def test_get_collections_sorted_alphabetically(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    for folder in ["zebra", "apple", "mango"]:
        db.upsert_book(
            conn,
            tmp_path / "books" / folder / "book.epub",
            {
                "title": folder,
                "author": None,
                "publisher": None,
                "year": None,
                "format": "epub",
                "cover_path": None,
            },
        )
    colls = db.get_collections(conn)
    names = [c["name"] for c in colls]
    assert names == sorted(names, key=str.lower)


def test_get_books_in_folder_basic(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    db.upsert_book(
        conn,
        tmp_path / "books" / "junji-ito" / "uzumaki.cbz",
        {
            "title": "Uzumaki",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "cbz",
            "cover_path": None,
        },
    )
    db.upsert_book(
        conn,
        tmp_path / "books" / "junji-ito" / "gyo.cbz",
        {
            "title": "Gyo",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "cbz",
            "cover_path": None,
        },
    )
    db.upsert_book(
        conn,
        tmp_path / "books" / "other" / "dune.epub",
        {
            "title": "Dune",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    results = db.get_books_in_folder(conn, "junji-ito")
    assert len(results) == 2
    titles = {b["title"] for b in results}
    assert titles == {"Uzumaki", "Gyo"}


def test_get_books_in_folder_uncategorized_includes_orphans(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    # Directly in root
    db.upsert_book(
        conn,
        tmp_path / "books" / "direct.epub",
        {
            "title": "Direct",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    # Orphaned (no matching root)
    db.upsert_book(
        conn,
        tmp_path / "orphan.epub",
        {
            "title": "Orphan",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    results = db.get_books_in_folder(conn, "Uncategorized")
    titles = {b["title"] for b in results}
    assert "Direct" in titles
    assert "Orphan" in titles


def test_get_books_in_folder_search(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    for title in ["Uzumaki", "Gyo", "Tomie"]:
        db.upsert_book(
            conn,
            tmp_path / "books" / "junji-ito" / f"{title}.cbz",
            {
                "title": title,
                "author": "Junji Ito",
                "publisher": None,
                "year": None,
                "format": "cbz",
                "cover_path": None,
            },
        )
    results = db.get_books_in_folder(conn, "junji-ito", query="uzumaki")
    assert len(results) == 1
    assert results[0]["title"] == "Uzumaki"


def test_get_books_in_folder_pagination(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    for i in range(5):
        db.upsert_book(
            conn,
            tmp_path / "books" / "series" / f"vol{i}.cbz",
            {
                "title": f"Vol {i}",
                "author": None,
                "publisher": None,
                "year": None,
                "format": "cbz",
                "cover_path": None,
            },
        )
    page1 = db.get_books_in_folder(conn, "series", limit=3, offset=0)
    page2 = db.get_books_in_folder(conn, "series", limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 2


def test_get_books_in_folder_deeply_nested(tmp_path):
    """Books nested multiple levels deep are attributed to the top-level subfolder."""
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    db.upsert_book(
        conn,
        tmp_path / "books" / "junji-ito" / "horror" / "uzumaki.cbz",
        {
            "title": "Uzumaki",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "cbz",
            "cover_path": None,
        },
    )
    results = db.get_books_in_folder(conn, "junji-ito")
    assert len(results) == 1
    assert results[0]["title"] == "Uzumaki"


def test_get_books_in_folder_nonexistent_folder_returns_empty(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    db.upsert_book(
        conn,
        tmp_path / "books" / "junji-ito" / "uzumaki.cbz",
        {
            "title": "Uzumaki",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "cbz",
            "cover_path": None,
        },
    )
    results = db.get_books_in_folder(conn, "nonexistent-folder")
    assert results == []
