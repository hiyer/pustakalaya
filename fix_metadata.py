#!/usr/bin/env python3
"""Update metadata for PDF and CBZ files.

By default, sets each file's title to its filename stem.
CBR files are not supported (RAR format is read-only).

For PDFs:  title/author/genre written to PDF metadata fields.
For CBZs:  title/author/genre written to ComicInfo.xml inside the archive.
           Genre uses the <Genre> element; author uses <Writer>.

Usage:
    python fix_metadata.py [options] file [file2 ...]
    python fix_metadata.py [options] /path/to/directory

Options:
    --author "Name"   Set author for all matched files
    --genre "Genre"   Set genre for all matched files
    --no-title        Skip updating the title
    --dry-run         Preview changes without writing
"""

import argparse
import io
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import fitz


# --- PDF ---

def fix_pdf(path: Path, title: str | None, author: str | None, genre: str | None, dry_run: bool) -> None:
    if title is None and author is None and genre is None:
        return

    with fitz.open(str(path)) as doc:
        meta = dict(doc.metadata or {})
        changes: list[str] = []

        if title is not None and meta.get("title") != title:
            changes.append(f"title: {meta.get('title')!r} -> {title!r}")
            meta["title"] = title

        if author is not None and meta.get("author") != author:
            changes.append(f"author: {meta.get('author')!r} -> {author!r}")
            meta["author"] = author

        if genre is not None and meta.get("subject") != genre:
            changes.append(f"genre: {meta.get('subject')!r} -> {genre!r}")
            meta["subject"] = genre

        if not changes:
            print(f"  skip  {path.name}  (already correct)")
            return

        print(f"  {'would set' if dry_run else 'set'}  {path.name!r}  {',  '.join(changes)}")
        if not dry_run:
            doc.set_metadata(meta)
            doc.saveIncr()


# --- CBZ ---

_COMIC_INFO_FIELD = {
    "title": "Title",
    "author": "Writer",
    "genre": "Genre",
}


def _build_comic_info(current: dict, updates: dict) -> bytes:
    """Merge updates into current ComicInfo dict and return XML bytes."""
    root = ElementTree.Element("ComicInfo")
    merged = {**current, **{k: v for k, v in updates.items() if v is not None}}
    for key, tag in _COMIC_INFO_FIELD.items():
        if key in merged:
            el = ElementTree.SubElement(root, tag)
            el.text = str(merged[key])
    # Preserve any other existing tags not in our mapping
    known_tags = set(_COMIC_INFO_FIELD.values())
    for tag, value in current.items():
        if tag not in known_tags:
            el = ElementTree.SubElement(root, tag)
            el.text = str(value)
    ElementTree.indent(root)
    return ElementTree.tostring(root, encoding="unicode", xml_declaration=False).encode()


def _read_comic_info(xml_bytes: bytes) -> dict:
    """Parse ComicInfo.xml into a flat tag->text dict."""
    try:
        root = ElementTree.fromstring(xml_bytes)
        return {el.tag: el.text for el in root if el.text}
    except Exception:
        return {}


def fix_cbz(path: Path, title: str | None, author: str | None, genre: str | None, dry_run: bool) -> None:
    if title is None and author is None and genre is None:
        return

    updates = {"title": title, "author": author, "genre": genre}

    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        comic_info_name = next(
            (n for n in names if Path(n).name.lower() == "comicinfo.xml"), None
        )
        current_raw = zf.read(comic_info_name) if comic_info_name else None
        current = _read_comic_info(current_raw) if current_raw else {}

        # Map our keys to ComicInfo tags to check current values
        tag_map = {"title": "Title", "author": "Writer", "genre": "Genre"}
        changes: list[str] = []
        for key, value in updates.items():
            if value is None:
                continue
            tag = tag_map[key]
            if current.get(tag) != value:
                changes.append(f"{key}: {current.get(tag)!r} -> {value!r}")

        if not changes:
            print(f"  skip  {path.name}  (already correct)")
            return

        print(f"  {'would set' if dry_run else 'set'}  {path.name!r}  {',  '.join(changes)}")
        if dry_run:
            return

        # Rewrite the zip with updated ComicInfo.xml
        new_xml = _build_comic_info(current, {tag_map[k]: v for k, v in updates.items() if v is not None})
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for name in names:
                if Path(name).name.lower() == "comicinfo.xml":
                    continue
                out.writestr(name, zf.read(name))
            out.writestr(comic_info_name or "ComicInfo.xml", new_xml)

    path.write_bytes(buf.getvalue())


# --- main ---

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="+", metavar="PATH", help="Files or directories")
    parser.add_argument("--author", metavar="NAME", help="Set author for all matched files")
    parser.add_argument("--genre", metavar="GENRE", help="Set genre for all matched files")
    parser.add_argument("--no-title", action="store_true", help="Skip updating the title")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    SUPPORTED = {".pdf", ".cbz"}
    files: list[Path] = []
    for arg in args.paths:
        p = Path(arg)
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED))
        elif p.suffix.lower() in SUPPORTED:
            files.append(p)
        elif p.suffix.lower() == ".cbr":
            print(f"  skip  {p.name}  (CBR is read-only; convert to .cbz if possible)", file=sys.stderr)
        else:
            print(f"  skip  {p.name}  (unsupported format)", file=sys.stderr)

    if not files:
        print("No supported files found.")
        sys.exit(0)

    for path in files:
        title = None if args.no_title else path.stem
        try:
            if path.suffix.lower() == ".pdf":
                fix_pdf(path, title=title, author=args.author, genre=args.genre, dry_run=args.dry_run)
            elif path.suffix.lower() == ".cbz":
                fix_cbz(path, title=title, author=args.author, genre=args.genre, dry_run=args.dry_run)
        except Exception as e:
            print(f"  ERROR  {path.name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
