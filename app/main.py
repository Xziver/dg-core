"""dg-engine — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import admin, bot, web
from app.infra.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    # Startup: create tables (dev mode)
    await init_db()
    yield


app = FastAPI(
    title="dg-engine",
    description="Digital Ghost World Engine — TRPG game engine service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(admin.router)
app.include_router(bot.router)
app.include_router(web.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "engine": "dg-engine", "version": "0.1.0"}
