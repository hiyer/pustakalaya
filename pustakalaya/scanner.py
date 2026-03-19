# pustakalaya/scanner.py
import io
import sqlite3
import zipfile
from pathlib import Path, PurePosixPath
from typing import TypedDict
from xml.etree import ElementTree

import fitz  # pymupdf
from PIL import Image

from pustakalaya import db

SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".cbz", ".cbr"}


class BookMetadata(TypedDict):
    title: str | None
    author: str | None
    publisher: str | None
    year: int | None
    format: str
    cover_data: bytes | None  # raw image bytes (any format)


def extract_metadata(path: Path) -> BookMetadata:
    ext = path.suffix.lower()
    if ext == ".epub":
        return _extract_epub(path)
    elif ext == ".pdf":
        return _extract_pdf(path)
    elif ext == ".cbz":
        return _extract_cbz(path)
    elif ext == ".cbr":
        return _extract_cbr(path)
    raise ValueError(f"Unsupported extension: {ext}")


def _safe_year(value: str | None, start: int = 0, length: int = 4) -> int | None:
    if not value:
        return None
    try:
        return int(value[start : start + length])
    except (ValueError, TypeError):
        return None


def _jpeg_from_bytes(data: bytes) -> bytes:
    """Decode image bytes and return JPEG bytes (RGB)."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _extract_epub(path: Path) -> BookMetadata:
    """Parse EPUB metadata directly from the OPF file inside the zip."""
    NS = {
        "dc": "http://purl.org/dc/elements/1.1/",
        "opf": "http://www.idpf.org/2007/opf",
    }

    def _text(root, xpath):
        el = root.find(xpath, NS)
        return el.text.strip() if el is not None and el.text else None

    try:
        with zipfile.ZipFile(path) as zf:
            # Locate OPF from container.xml
            container_xml = zf.read("META-INF/container.xml")
            container = ElementTree.fromstring(container_xml)
            opf_path = container.find(
                ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
            ).get("full-path")

            opf_xml = zf.read(opf_path)
            opf = ElementTree.fromstring(opf_xml)

            metadata = opf.find("opf:metadata", NS)

            title = _text(metadata, "dc:title")
            author = _text(metadata, "dc:creator")
            publisher = _text(metadata, "dc:publisher")
            date_str = _text(metadata, "dc:date")

            # Find cover image: look for <meta name="cover" content="..."/> id
            cover_data = None
            cover_id = None
            for meta_el in metadata.findall("opf:meta", NS):
                if meta_el.get("name") == "cover":
                    cover_id = meta_el.get("content")
                    break

            OPF_NS = "http://www.idpf.org/2007/opf"
            opf_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""

            if cover_id:
                # Find item in manifest with this id
                manifest = opf.find("opf:manifest", NS)
                for item in manifest.findall("opf:item", NS):
                    if item.get("id") == cover_id:
                        href = item.get("href")
                        img_path = f"{opf_dir}/{href}" if opf_dir else href
                        try:
                            img_data = zf.read(img_path)
                            cover_data = _jpeg_from_bytes(img_data)
                        except Exception:
                            pass
                        break

            # EPUB 3 fallback: manifest item with properties="cover-image"
            if cover_data is None:
                for item in opf.findall(f"{{{OPF_NS}}}manifest/{{{OPF_NS}}}item"):
                    if "cover-image" in (item.get("properties") or "").split():
                        href = item.get("href")
                        if href:
                            cover_path_in_zip = str(
                                PurePosixPath(opf_dir) / href
                            ).lstrip("/")
                            try:
                                cover_data = _jpeg_from_bytes(
                                    zf.read(cover_path_in_zip)
                                )
                            except Exception:
                                pass
                        break

        return BookMetadata(
            title=title or path.stem,
            author=author,
            publisher=publisher,
            year=_safe_year(date_str, 0, 4),
            format="epub",
            cover_data=cover_data,
        )
    except Exception:
        return _fallback(path, "epub")


def _extract_pdf(path: Path) -> BookMetadata:
    try:
        with fitz.open(str(path)) as doc:
            meta = doc.metadata or {}

            cover_data = None
            try:
                page = doc.load_page(0)
                pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
                cover_data = _jpeg_from_bytes(pix.tobytes("png"))
            except Exception:
                pass

        return BookMetadata(
            title=meta.get("title") or path.stem or None,
            author=meta.get("author") or None,
            publisher=None,
            year=_safe_year(meta.get("creationDate"), 2, 4),
            format="pdf",
            cover_data=cover_data,
        )
    except Exception:
        return _fallback(path, "pdf")


def _parse_comic_info(xml_bytes: bytes) -> dict:
    try:
        root = ElementTree.fromstring(xml_bytes)

        def text(tag):
            el = root.find(tag)
            return el.text.strip() if el is not None and el.text else None

        def intval(tag):
            v = text(tag)
            try:
                return int(v) if v else None
            except ValueError:
                return None

        return {
            "title": text("Title"),
            "author": text("Writer"),
            "publisher": text("Publisher"),
            "year": intval("Year"),
        }
    except Exception:
        return {}


def _find_comic_info(names: list[str]) -> str | None:
    """Find ComicInfo.xml anywhere in the archive, case-insensitively."""
    for name in names:
        if Path(name).name.lower() == "comicinfo.xml":
            return name
    return None


def _first_image_bytes(names: list[str], read_fn) -> bytes | None:
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    for name in sorted(names):
        if Path(name).suffix.lower() in image_exts:
            try:
                data = read_fn(name)
                return _jpeg_from_bytes(data)
            except Exception:
                continue
    return None


def _extract_cbz(path: Path) -> BookMetadata:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            info = {}
            comic_info_name = _find_comic_info(names)
            if comic_info_name:
                info = _parse_comic_info(zf.read(comic_info_name))
            cover_data = _first_image_bytes(names, zf.read)
        return BookMetadata(
            title=info.get("title") or path.stem,
            author=info.get("author"),
            publisher=info.get("publisher"),
            year=info.get("year"),
            format="cbz",
            cover_data=cover_data,
        )
    except Exception:
        return _fallback(path, "cbz")


def _extract_cbr(path: Path) -> BookMetadata:
    try:
        import rarfile

        with rarfile.RarFile(str(path)) as rf:
            names = rf.namelist()
            info = {}
            comic_info_name = _find_comic_info(names)
            if comic_info_name:
                info = _parse_comic_info(rf.read(comic_info_name))
            cover_data = _first_image_bytes(names, rf.read)
        return BookMetadata(
            title=info.get("title") or path.stem,
            author=info.get("author"),
            publisher=info.get("publisher"),
            year=info.get("year"),
            format="cbr",
            cover_data=cover_data,
        )
    except Exception:
        return _fallback(path, "cbr")


def _fallback(path: Path, fmt: str) -> BookMetadata:
    return BookMetadata(
        title=path.stem,
        author=None,
        publisher=None,
        year=None,
        format=fmt,
        cover_data=None,
    )


def scan_file(
    conn: sqlite3.Connection,
    path: Path,
    covers_dir: Path,
) -> int:
    """Extract metadata from a file, save cover, upsert to DB. Returns book id."""
    meta = extract_metadata(path)

    # Preserve existing cover_path if we have no new cover data
    existing = db.get_book_by_path(conn, path)
    existing_cover = existing["cover_path"] if existing else None

    book_id = db.upsert_book(
        conn,
        path,
        {
            "title": meta["title"],
            "author": meta["author"],
            "publisher": meta["publisher"],
            "year": meta["year"],
            "format": meta["format"],
            "cover_path": existing_cover,  # preserve existing; overwrite below only if we have new data
        },
    )

    if meta["cover_data"]:
        cover_path = covers_dir / f"{book_id}.jpg"
        cover_path.write_bytes(meta["cover_data"])
        db.update_cover(conn, book_id, str(cover_path))

    return book_id


def scan_all(conn: sqlite3.Connection, covers_dir: Path) -> None:
    """Full scan of all library roots: upsert new/changed, delete stale."""
    roots = db.get_library_roots(conn)
    found_paths: set[str] = set()

    for root_row in roots:
        root = Path(root_row["path"])
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if path.is_file():
                try:
                    scan_file(conn, path, covers_dir)
                    found_paths.add(str(path))
                except Exception:
                    pass

    # Delete books whose files no longer exist under any root
    all_books = db.get_all_books(conn)
    for book in all_books:
        if book["path"] not in found_paths:
            db.delete_book(conn, Path(book["path"]))
