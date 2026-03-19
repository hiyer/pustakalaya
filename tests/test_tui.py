# tests/test_tui.py
import pytest
from pustakalaya import db


@pytest.fixture()
def db_conn(tmp_path):
    conn = db.init(tmp_path / "library.db")
    db.upsert_book(
        conn,
        tmp_path / "dune.epub",
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "publisher": None,
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
    return conn


@pytest.fixture()
def covers_dir(tmp_path):
    d = tmp_path / "covers"
    d.mkdir()
    return d


@pytest.mark.asyncio
async def test_app_starts(db_conn, covers_dir):
    from pustakalaya.tui.app import PustakalayaApp

    app = PustakalayaApp(conn=db_conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # TabbedContent should be mounted
        from textual.widgets import TabbedContent

        assert app.query_one(TabbedContent) is not None


@pytest.mark.asyncio
async def test_books_tab_shows_books(db_conn, covers_dir):
    from pustakalaya.tui.app import PustakalayaApp
    from textual.widgets import DataTable

    app = PustakalayaApp(conn=db_conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        table = app.query_one(DataTable)
        assert table.row_count == 2


@pytest.mark.asyncio
async def test_search_filters_books(db_conn, covers_dir):
    from pustakalaya.tui.app import PustakalayaApp
    from textual.widgets import DataTable, Input

    app = PustakalayaApp(conn=db_conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("/")
        # pilot.type() not available in this version; press each character
        for ch in "dune":
            await pilot.press(ch)
        await pilot.pause()
        table = app.query_one(DataTable)
        assert table.row_count == 1


@pytest.mark.asyncio
async def test_quit_key(db_conn, covers_dir):
    from pustakalaya.tui.app import PustakalayaApp

    app = PustakalayaApp(conn=db_conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("q")


@pytest.mark.asyncio
async def test_open_book_with_selection_calls_xdg_open(db_conn, covers_dir):
    from pustakalaya.tui.app import PustakalayaApp

    app = PustakalayaApp(conn=db_conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # mock xdg-open to avoid actually opening anything
        import subprocess

        called_with = []
        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            called_with.extend(cmd)

            class R:
                returncode = 0
                stderr = b""

            return R()

        import unittest.mock

        with unittest.mock.patch("subprocess.run", mock_run):
            await pilot.press("down")  # select first row
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
        assert "xdg-open" in called_with


@pytest.mark.asyncio
async def test_open_book_xdg_error_shows_notification(db_conn, covers_dir):
    import subprocess, unittest.mock
    from pustakalaya.tui.app import PustakalayaApp

    app = PustakalayaApp(conn=db_conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        def mock_run(cmd, **kwargs):
            class R:
                returncode = 1
                stderr = b"No application found"

            return R()

        with unittest.mock.patch("subprocess.run", mock_run):
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("o")
            await pilot.pause()
        # Textual stores notifications in app._notifications
        assert len(app._notifications) > 0


@pytest.mark.asyncio
async def test_open_book_with_no_selection_notifies(tmp_path, covers_dir):
    """Pressing 'o' with no row selected shows a warning, not an exception."""
    from pustakalaya import db as pdb
    from pustakalaya.tui.app import PustakalayaApp

    # Empty library — no books in table, so cursor_row never has a valid selection
    conn = pdb.init(tmp_path / "empty.db")
    app = PustakalayaApp(conn=conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        # Textual stores notifications in app._notifications
        assert len(app._notifications) > 0


@pytest.mark.asyncio
async def test_roots_pane_shows_roots(tmp_path, covers_dir):
    from pustakalaya import db

    conn = db.init(tmp_path / "library.db")
    db.add_library_root(conn, tmp_path / "books")
    from pustakalaya.tui.app import PustakalayaApp
    from textual.widgets import ListView

    app = PustakalayaApp(conn=conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        # Switch to roots tab
        await pilot.press("ctrl+tab")  # or click tab
        await pilot.pause()
        # roots pane should exist
        from pustakalaya.tui.screens.roots import RootsPane

        assert app.query_one(RootsPane) is not None


@pytest.mark.asyncio
async def test_metadata_modal_cancel(db_conn, covers_dir):
    from pustakalaya.tui.app import PustakalayaApp
    from pustakalaya.tui.screens.metadata import MetadataModal

    app = PustakalayaApp(conn=db_conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Switch to Books tab first (Library Roots is default tab)
        await pilot.press("ctrl+tab")
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, MetadataModal)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, MetadataModal)


@pytest.mark.asyncio
async def test_metadata_modal_saves_to_db(db_conn, covers_dir):
    from pustakalaya.tui.app import PustakalayaApp
    from pustakalaya.tui.screens.metadata import MetadataModal
    from textual.widgets import Input
    from pustakalaya import db as pdb

    app = PustakalayaApp(conn=db_conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Switch to Books tab first (Library Roots is default tab)
        await pilot.press("ctrl+tab")
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, MetadataModal)
        # Clear title field and type a new value
        title_input = app.screen.query_one("#f-title", Input)
        title_input.value = "Updated Title"
        await pilot.pause()
        # Press Save button
        await pilot.click("#btn-save")
        await pilot.pause()
        # Modal should be gone
        assert not isinstance(app.screen, MetadataModal)
        # DB should be updated
        books = pdb.get_all_books(db_conn, query="Updated")
        assert len(books) == 1


@pytest.mark.asyncio
async def test_metadata_save_db_error_keeps_modal_open(db_conn, covers_dir):
    """If DB write fails, the modal stays open and a notification is shown."""
    import unittest.mock
    from pustakalaya.tui.app import PustakalayaApp
    from pustakalaya.tui.screens.metadata import MetadataModal

    app = PustakalayaApp(conn=db_conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Switch to Books tab first (Library Roots is default tab)
        await pilot.press("ctrl+tab")
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, MetadataModal)
        # Patch db.upsert_book to raise
        with unittest.mock.patch(
            "pustakalaya.db.upsert_book", side_effect=Exception("disk full")
        ):
            await pilot.click("#btn-save")
            await pilot.pause()
        # Modal must still be on screen
        assert isinstance(app.screen, MetadataModal)
        # A notification must have been shown (check via app._notifications)
        assert len(app._notifications) > 0


@pytest.mark.asyncio
async def test_watcher_root_added_to_observer(tmp_path, covers_dir):
    """Adding a root via the UI should call watcher.add_root()."""
    from pustakalaya import db as pdb
    from pustakalaya.tui.app import PustakalayaApp
    import unittest.mock

    conn = pdb.init(tmp_path / "library.db")
    app = PustakalayaApp(conn=conn, covers_dir=covers_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app._watcher is not None
        books_dir = tmp_path / "mybooks"
        books_dir.mkdir()
        with unittest.mock.patch.object(app._watcher, "add_root") as mock_add:
            # Switch to roots tab (it's already the first tab / default)
            await pilot.pause()
            path_input = app.query_one("#path-input")
            # Set the input value directly
            path_input.value = str(books_dir)
            await pilot.pause()
            # Focus the button and press Enter (pilot.click doesn't work inside tabs)
            app.query_one("#btn-add").focus()
            await pilot.press("enter")
            await pilot.pause()
            mock_add.assert_called_once_with(books_dir)
