# tests/test_scanner.py
from pathlib import Path
import pytest
from pustakalaya import scanner

# --- Metadata extraction ---


def test_extract_epub(epub_path):
    m = scanner.extract_metadata(epub_path)
    assert m["title"] == "Test EPUB Title"
    assert m["author"] == "EPUB Author"
    assert m["publisher"] == "EPUB Publisher"
    assert m["year"] == 2001
    assert m["format"] == "epub"
    assert m["cover_data"] is not None


def test_extract_epub3_cover(epub3_cover_path):
    m = scanner.extract_metadata(epub3_cover_path)
    assert m["title"] == "EPUB3 Book"
    assert m["author"] == "EPUB3 Author"
    assert m["cover_data"] is not None


def test_extract_epub_no_meta(epub_no_meta_path):
    m = scanner.extract_metadata(epub_no_meta_path)
    assert m["title"] == "bare"  # filename stem fallback
    assert m["author"] is None
    assert m["year"] is None
    assert m["cover_data"] is None


def test_extract_pdf(pdf_path):
    m = scanner.extract_metadata(pdf_path)
    assert m["title"] == "Test PDF Title"
    assert m["author"] == "PDF Author"
    assert m["year"] == 2003
    assert m["format"] == "pdf"
    assert m["cover_data"] is not None


def test_extract_cbz(cbz_path):
    m = scanner.extract_metadata(cbz_path)
    assert m["title"] == "Test CBZ"
    assert m["author"] == "CBZ Writer"
    assert m["publisher"] == "CBZ Pub"
    assert m["year"] == 2010
    assert m["format"] == "cbz"
    assert m["cover_data"] is not None


def test_extract_cbz_no_meta(cbz_no_meta_path):
    m = scanner.extract_metadata(cbz_no_meta_path)
    assert m["title"] == "bare"
    assert m["cover_data"] is not None  # still has first image


def test_extract_unsupported_extension(tmp_path):
    p = tmp_path / "book.mobi"
    p.write_bytes(b"junk")
    with pytest.raises(ValueError, match="Unsupported"):
        scanner.extract_metadata(p)


# --- scan_file ---


def test_scan_file_saves_book_and_cover(tmp_path, cbz_path):
    from pustakalaya import db

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()

    book_id = scanner.scan_file(conn, cbz_path, covers_dir)
    book = db.get_book(conn, book_id)
    assert book["title"] == "Test CBZ"
    assert book["cover_path"] is not None
    assert Path(book["cover_path"]).exists()


def test_scan_file_cover_is_jpeg(tmp_path, cbz_path):
    from pustakalaya import db
    from PIL import Image

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()

    book_id = scanner.scan_file(conn, cbz_path, covers_dir)
    cover_path = Path(db.get_book(conn, book_id)["cover_path"])
    img = Image.open(cover_path)
    assert img.format == "JPEG"
    assert img.mode == "RGB"


def test_scan_file_no_cover(tmp_path, epub_no_meta_path):
    from pustakalaya import db

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()

    book_id = scanner.scan_file(conn, epub_no_meta_path, covers_dir)
    book = db.get_book(conn, book_id)
    assert book["cover_path"] is None


def test_scan_file_preserves_cover_when_no_new_cover(tmp_path, cbz_path):
    """If re-scanning yields no cover_data, the existing cover_path is preserved."""
    from pustakalaya import db
    from unittest.mock import patch

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()

    # First scan: CBZ with cover
    book_id = scanner.scan_file(conn, cbz_path, covers_dir)
    original_cover = db.get_book(conn, book_id)["cover_path"]
    assert original_cover is not None

    # Second scan: same file but extraction returns no cover (simulated)
    with patch.object(scanner, "extract_metadata") as mock_meta:
        mock_meta.return_value = {
            "title": "Test CBZ",
            "author": "CBZ Writer",
            "publisher": "CBZ Pub",
            "year": 2010,
            "format": "cbz",
            "cover_data": None,
        }
        scanner.scan_file(conn, cbz_path, covers_dir)

    book = db.get_book(conn, book_id)
    assert book["cover_path"] == original_cover  # NOT wiped


# --- scan_all ---


def test_scan_all_inserts_books(tmp_path, cbz_path):
    import shutil
    from pustakalaya import db

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    shutil.copy(cbz_path, books_dir / "test.cbz")
    db.add_library_root(conn, books_dir)

    scanner.scan_all(conn, covers_dir)
    books = db.get_all_books(conn)
    assert len(books) == 1
    assert books[0]["title"] == "Test CBZ"


def test_scan_all_removes_stale(tmp_path):
    from pustakalaya import db

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    books_dir = tmp_path / "books"
    books_dir.mkdir()

    # Manually add a path that doesn't exist on disk
    db.upsert_book(
        conn,
        Path("/nonexistent/ghost.epub"),
        {
            "title": "Ghost",
            "author": None,
            "publisher": None,
            "year": None,
            "format": "epub",
            "cover_path": None,
        },
    )
    db.add_library_root(conn, books_dir)
    scanner.scan_all(conn, covers_dir)

    assert db.get_all_books(conn) == []


def test_scan_all_ignores_non_book_files(tmp_path):
    from pustakalaya import db

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "readme.txt").write_text("ignore me")
    (books_dir / "image.jpg").write_bytes(b"junk")
    db.add_library_root(conn, books_dir)

    scanner.scan_all(conn, covers_dir)
    assert db.get_all_books(conn) == []


def test_scan_all_is_recursive(tmp_path, cbz_path):
    import shutil
    from pustakalaya import db

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    sub = tmp_path / "books" / "subdir"
    sub.mkdir(parents=True)
    shutil.copy(cbz_path, sub / "test.cbz")
    db.add_library_root(conn, tmp_path / "books")
    scanner.scan_all(conn, covers_dir)
    assert len(db.get_all_books(conn)) == 1


# --- watcher handler ---


def test_watcher_handler_created_file(tmp_path, cbz_path):
    import shutil
    from pustakalaya import db, watcher

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    dest = tmp_path / "copy.cbz"
    shutil.copy(cbz_path, dest)

    handler = watcher.LibraryEventHandler(conn, covers_dir)
    handler.on_created_or_moved_to(dest)

    assert len(db.get_all_books(conn)) == 1


def test_watcher_handler_deleted_file(tmp_path, cbz_path):
    import shutil
    from pustakalaya import db, watcher

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    dest = tmp_path / "copy.cbz"
    shutil.copy(cbz_path, dest)
    scanner.scan_file(conn, dest, covers_dir)
    assert len(db.get_all_books(conn)) == 1

    handler = watcher.LibraryEventHandler(conn, covers_dir)
    handler.on_deleted_or_moved_from(dest)
    assert db.get_all_books(conn) == []


def test_watcher_handler_ignores_non_book(tmp_path):
    from pustakalaya import db, watcher

    conn = db.init(tmp_path / "library.db")
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    txt = tmp_path / "readme.txt"
    txt.write_text("hello")

    handler = watcher.LibraryEventHandler(conn, covers_dir)
    handler.on_created_or_moved_to(txt)
    assert db.get_all_books(conn) == []
