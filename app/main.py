"""dg-core — FastAPI application entry point."""

from contextlib import asynccontextmanager
from importlib.metadata import version, PackageNotFoundError

from fastapi import FastAPI

from app.api import admin, auth, bot, web
from app.infra.db import init_db

try:
    __version__ = version("dg-core")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    # Startup: create tables (dev mode)
    await init_db()
    yield


app = FastAPI(
    title="dg-core",
    description="Digital Ghost World Engine — TRPG game engine service",
    version=__version__,
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(bot.router)
app.include_router(web.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "engine": "dg-core", "version": __version__}
