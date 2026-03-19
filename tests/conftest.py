# tests/conftest.py
import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image


def _tiny_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(100, 150, 200)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def epub_path(tmp_path) -> Path:
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_title("Test EPUB Title")
    book.add_author("EPUB Author")
    book.add_metadata("DC", "publisher", "EPUB Publisher")
    book.add_metadata("DC", "date", "2001-09-11")
    # add cover
    cover_item = epub.EpubItem(
        uid="cover-image",
        file_name="cover.jpg",
        media_type="image/jpeg",
        content=_tiny_jpeg_bytes(),
    )
    book.add_item(cover_item)
    book.set_cover("cover.jpg", _tiny_jpeg_bytes())
    out = tmp_path / "test.epub"
    epub.write_epub(str(out), book)
    return out


@pytest.fixture()
def epub_no_meta_path(tmp_path) -> Path:
    from ebooklib import epub

    book = epub.EpubBook()
    out = tmp_path / "bare.epub"
    epub.write_epub(str(out), book)
    return out


@pytest.fixture()
def pdf_path(tmp_path) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=100, height=100)
    page.insert_text((10, 50), "hello")
    doc.set_metadata(
        {
            "title": "Test PDF Title",
            "author": "PDF Author",
            "creationDate": "D:20030315120000",
        }
    )
    out = tmp_path / "test.pdf"
    doc.save(str(out))
    doc.close()
    return out


@pytest.fixture()
def cbz_path(tmp_path) -> Path:
    out = tmp_path / "test.cbz"
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr(
            "ComicInfo.xml",
            "<ComicInfo>"
            "<Title>Test CBZ</Title>"
            "<Writer>CBZ Writer</Writer>"
            "<Publisher>CBZ Pub</Publisher>"
            "<Year>2010</Year>"
            "</ComicInfo>",
        )
        zf.writestr("001.jpg", _tiny_jpeg_bytes())
        zf.writestr("002.jpg", _tiny_jpeg_bytes())
    return out


@pytest.fixture()
def cbz_no_meta_path(tmp_path) -> Path:
    out = tmp_path / "bare.cbz"
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("a.jpg", _tiny_jpeg_bytes())
    return out


@pytest.fixture()
def epub3_cover_path(tmp_path) -> Path:
    """EPUB 3 with cover-image manifest property (no EPUB 2 meta element)."""
    import zipfile as zf

    out = tmp_path / "epub3.epub"
    img_bytes = _tiny_jpeg_bytes()
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>EPUB3 Book</dc:title>"
        "<dc:creator>EPUB3 Author</dc:creator>"
        "</metadata>"
        "<manifest>"
        '<item id="cover-img" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>'
        "</manifest>"
        '<spine><itemref idref="cover-img"/></spine>'
        "</package>"
    )
    with zf.ZipFile(out, "w") as z:
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>'
            "</container>",
        )
        z.writestr("content.opf", opf)
        z.writestr("cover.jpg", img_bytes)
    return out
