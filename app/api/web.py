"""Web API — placeholder for future gRPC / WebSocket interface."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/web", tags=["web"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "message": "Web API not yet implemented. Use Bot API."}
