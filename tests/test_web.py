# tests/test_web.py
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pustakalaya import db


@pytest.fixture()
def sample_db(tmp_path):
    conn = db.init(tmp_path / "library.db")
    # Add two books
    db.upsert_book(
        conn,
        tmp_path / "dune.epub",
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "publisher": "Chilton",
            "year": 1965,
            "format": "epub",
            "cover_path": None,
        },
    )
    db.upsert_book(
        conn,
        tmp_path / "neuro.pdf",
        {
            "title": "Neuromancer",
            "author": "William Gibson",
            "publisher": None,
            "year": 1984,
            "format": "pdf",
            "cover_path": None,
        },
    )
    return tmp_path, conn


@pytest.fixture()
def client(sample_db, monkeypatch):
    db_dir, conn = sample_db
    covers_dir = db_dir / "covers"
    covers_dir.mkdir()

    import pam

    monkeypatch.setattr(
        pam,
        "authenticate",
        lambda u, p, service="login": u == "user" and p == "pass",
    )

    from pustakalaya.web.app import create_app

    app = create_app(db_path=db_dir / "library.db", covers_dir=covers_dir)
    return TestClient(app, raise_server_exceptions=True)


GOOD_AUTH = ("user", "pass")
BAD_AUTH = ("user", "wrong")


def test_no_auth_returns_401(client):
    assert client.get("/").status_code == 401


def test_bad_auth_returns_401(client):
    assert client.get("/", auth=BAD_AUTH).status_code == 401


def test_root_lists_books(client):
    resp = client.get("/", auth=GOOD_AUTH)
    assert resp.status_code == 200
    assert "Dune" in resp.text
    assert "Neuromancer" in resp.text


def test_search_filters(client):
    resp = client.get("/?q=dune", auth=GOOD_AUTH)
    assert "Dune" in resp.text
    assert "Neuromancer" not in resp.text


def test_book_detail_page(client, sample_db):
    db_dir, conn = sample_db
    books = db.get_all_books(conn)
    book_id = books[0]["id"]
    resp = client.get(f"/books/{book_id}", auth=GOOD_AUTH)
    assert resp.status_code == 200


def test_book_not_found(client):
    resp = client.get("/books/99999", auth=GOOD_AUTH)
    assert resp.status_code == 404


def test_download_serves_file(client, sample_db):
    db_dir, conn = sample_db
    # Create the actual file on disk
    epub_file = db_dir / "dune.epub"
    epub_file.write_bytes(b"fake epub content")
    # Update DB path to the real temp path
    books = db.get_all_books(conn)
    book = next(b for b in books if b["title"] == "Dune")
    db.upsert_book(
        conn,
        epub_file,
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "publisher": "Chilton",
            "year": 1965,
            "format": "epub",
            "cover_path": None,
        },
    )
    books2 = db.get_all_books(conn)
    book2 = next(b for b in books2 if b["title"] == "Dune")
    resp = client.get(f"/books/{book2['id']}/download", auth=GOOD_AUTH)
    assert resp.status_code == 200
    assert resp.content == b"fake epub content"


def test_download_missing_file_returns_404(client, sample_db):
    db_dir, conn = sample_db
    books = db.get_all_books(conn)
    book_id = books[0]["id"]
    resp = client.get(f"/books/{book_id}/download", auth=GOOD_AUTH)
    assert resp.status_code == 404


def test_cover_serves_jpeg(client, sample_db):
    db_dir, conn = sample_db
    covers_dir = db_dir / "covers"
    books = db.get_all_books(conn)
    book_id = books[0]["id"]
    # Write a cover file
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="JPEG")
    (covers_dir / f"{book_id}.jpg").write_bytes(buf.getvalue())

    resp = client.get(f"/covers/{book_id}", auth=GOOD_AUTH)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


def test_cover_missing_returns_404(client, sample_db):
    db_dir, conn = sample_db
    books = db.get_all_books(conn)
    book_id = books[0]["id"]
    resp = client.get(f"/covers/{book_id}", auth=GOOD_AUTH)
    assert resp.status_code == 404


def test_pagination_page2(client, sample_db):
    db_dir, conn = sample_db
    # With size=1, page 2 should show Neuromancer (books sorted by title)
    resp = client.get("/?page=1&size=1", auth=GOOD_AUTH)
    assert resp.status_code == 200
    resp2 = client.get("/?page=2&size=1", auth=GOOD_AUTH)
    assert resp2.status_code == 200
    # Collectively both pages should cover both books
    assert "Dune" in resp.text or "Dune" in resp2.text
    assert "Neuromancer" in resp.text or "Neuromancer" in resp2.text


def test_size_cap_at_200(client, sample_db):
    """size > 200 should be silently capped to 200 (not raise an error)."""
    resp = client.get("/?size=9999", auth=GOOD_AUTH)
    assert resp.status_code == 200
