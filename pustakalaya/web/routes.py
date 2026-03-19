# pustakalaya/web/routes.py
import sqlite3
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


def _conn(request: Request) -> sqlite3.Connection:
    return request.app.state.conn


@router.get("/", response_class=HTMLResponse)
def index(request: Request, q: str = "", page: int = 1, size: int = 50):
    size = min(size, 200)
    offset = (page - 1) * size
    books = db.get_all_books(_conn(request), query=q, limit=size, offset=offset)
    return _templates.TemplateResponse(
        request,
        "index.html",
        {"books": books, "q": q, "page": page},
    )


@router.get("/books/{book_id}", response_class=HTMLResponse)
def book_detail(request: Request, book_id: int):
    book = db.get_book(_conn(request), book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return _templates.TemplateResponse(
        request,
        "book.html",
        {"book": book},
    )


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
