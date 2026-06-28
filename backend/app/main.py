"""FastAPI application entry point.

Serves the JSON API under /api and the static PWA frontend at /.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import SessionLocal
from .routers import aircraft, dashboard, items
from .seed import init_db, seed_catalog

app = FastAPI(title="SBSF Maintenance Hub", version="0.1.0")

app.include_router(aircraft.router)
app.include_router(items.router)
app.include_router(dashboard.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_catalog(db)  # ensure the catalog exists; idempotent
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


# --- Static frontend (mounted last so /api takes precedence) -----------------
_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
_FRONTEND_DIR = os.path.abspath(_FRONTEND_DIR)

if os.path.isdir(_FRONTEND_DIR):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))

    app.mount("/", StaticFiles(directory=_FRONTEND_DIR), name="frontend")
