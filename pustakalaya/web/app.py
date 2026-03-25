# pustakalaya/web/app.py
from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pustakalaya import db
from pustakalaya.web.auth import PamBasicAuthMiddleware
from pustakalaya.web.routes import configure, router

_PACKAGE_DIR = Path(__file__).parent.parent
_TEMPLATES_DIR = _PACKAGE_DIR / "templates"
_STATIC_DIR = _PACKAGE_DIR / "static"


def create_app(
    db_path: Path | None = None,
    covers_dir: Path | None = None,
) -> FastAPI:
    _DATA_DIR = (
        Path.home() / ".local" / "share" / "pustakalaya"
    )  # runtime, not import-time
    db_path = db_path or (_DATA_DIR / "library.db")
    covers_dir = covers_dir or (_DATA_DIR / "covers")

    app = FastAPI(title="pustakalaya", docs_url=None, redoc_url=None)
    app.add_middleware(PamBasicAuthMiddleware)

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    configure(templates, covers_dir)

    app.state.conn = db.init(db_path)
    app.include_router(router)

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Pustakalaya web server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7788)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(create_app(), host=args.host, port=args.port)
