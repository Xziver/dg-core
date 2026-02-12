"""Web API — WebSocket real-time game updates."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.domain.dispatcher import dispatch
from app.infra.auth import decode_access_token
from app.infra.db import async_session_factory
from app.infra.ws_manager import ws_manager
from app.models.event import GameEvent

router = APIRouter(prefix="/api/web", tags=["web"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "message": "Web API active."}


@router.websocket("/ws/{game_id}")
async def websocket_game(websocket: WebSocket, game_id: str) -> None:
    """WebSocket endpoint for real-time game updates.

    Connect with: ws://host/api/web/ws/{game_id}?token=<jwt_token>

    On connect: authenticates via query param token, joins game room.
    Receives: JSON game events (same format as POST /api/bot/events payload field).
    Sends: EngineResult JSON for all events in the game.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        token_data = decode_access_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = token_data.user_id
    await ws_manager.connect(game_id, user_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            try:
                event = GameEvent(
                    game_id=game_id,
                    user_id=user_id,
                    session_id=data.get("session_id"),
                    payload=data.get("payload", {}),
                )
                async with async_session_factory() as db:
                    try:
                        result = await dispatch(db, event)
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        raise

                await ws_manager.broadcast_to_game(game_id, result)
            except Exception as exc:
                await websocket.send_json({"success": False, "error": str(exc)})
    except WebSocketDisconnect:
        ws_manager.disconnect(game_id, user_id)
