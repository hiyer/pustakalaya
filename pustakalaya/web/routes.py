# pustakalaya/web/routes.py
import sqlite3
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from pustakalaya import db

router = APIRouter()

_templates: Jinja2Templates | None = None
_covers_dir: Path | None = None


def configure(templates: Jinja2Templates, covers_dir: Path) -> None:
    global _templates, _covers_dir
    _templates = templates
    _covers_dir = covers_dir
    _templates.env.filters["quote_path"] = lambda s: urllib.parse.quote(str(s), safe="")


def _conn(request: Request) -> sqlite3.Connection:
    return request.app.state.conn


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    collections = db.get_collections(_conn(request))
    return _templates.TemplateResponse(
        request, "collections.html", {"collections": collections}
    )


@router.get("/books", response_class=HTMLResponse)
def all_books(request: Request, q: str = "", page: int = 1, size: int = 50):
    size = min(size, 200)
    offset = (page - 1) * size
    books = db.get_all_books(_conn(request), query=q, limit=size, offset=offset)
    return _templates.TemplateResponse(
        request, "index.html", {"books": books, "q": q, "page": page, "folder": None}
    )


@router.get("/collections/{folder}", response_class=HTMLResponse)
def collection_books(
    request: Request, folder: str, q: str = "", page: int = 1, size: int = 50
):
    # Verify the collection exists
    known = {c["name"] for c in db.get_collections(_conn(request))}
    if folder not in known:
        raise HTTPException(status_code=404, detail="Collection not found")
    size = min(size, 200)
    offset = (page - 1) * size
    books = db.get_books_in_folder(
        _conn(request), folder, query=q, limit=size, offset=offset
    )
    return _templates.TemplateResponse(
        request,
        "index.html",
        {"books": books, "q": q, "page": page, "folder": folder},
    )


@router.get("/roots", response_class=HTMLResponse)
def roots(request: Request):
    library_roots = db.get_library_roots(_conn(request))
    return _templates.TemplateResponse(request, "roots.html", {"roots": library_roots})


@router.get("/books/{book_id}", response_class=HTMLResponse)
def book_detail(request: Request, book_id: int):
    book = db.get_book(_conn(request), book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return _templates.TemplateResponse(request, "book.html", {"book": book})


@router.get("/books/{book_id}/download")
def download(request: Request, book_id: int):
    book = db.get_book(_conn(request), book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    path = Path(book["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type="application/octet-stream",
    )


@router.get("/covers/{book_id}")
def cover(book_id: int):
    cover_file = _covers_dir / f"{book_id}.jpg"
    if not cover_file.exists():
        raise HTTPException(status_code=404, detail="Cover not found")
    return FileResponse(str(cover_file), media_type="image/jpeg")
