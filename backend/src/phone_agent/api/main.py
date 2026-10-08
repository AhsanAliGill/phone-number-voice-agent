from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..config import get_settings
from .db import Database
from .routes import router

# backend/src/phone_agent/api/main.py -> <repo>/frontend
DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[4] / "frontend"


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db.create_all()
        yield

    app = FastAPI(title="Phone Number Collection API", version="0.1.0", lifespan=lifespan)
    app.state.db = Database(database_url or settings.database_url)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    # Serve the frontend (plain HTML/JS) at "/" so one command runs everything.
    # Mounted after the API routes, so /api/* is never shadowed.
    frontend_dir = Path(settings.frontend_dir) if settings.frontend_dir else DEFAULT_FRONTEND_DIR
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("phone_agent.api.main:app", host=settings.api_host, port=settings.api_port)
