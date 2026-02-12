"""WebSocket connection manager — broadcasts EngineResults to connected clients."""

from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket

from app.models.result import EngineResult


class ConnectionManager:
    """Manages WebSocket connections grouped by game_id."""

    def __init__(self) -> None:
        self._connections: dict[str, dict[str, WebSocket]] = defaultdict(dict)

    async def connect(self, game_id: str, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[game_id][user_id] = websocket

    def disconnect(self, game_id: str, user_id: str) -> None:
        self._connections[game_id].pop(user_id, None)
        if not self._connections[game_id]:
            del self._connections[game_id]

    async def broadcast_to_game(self, game_id: str, result: EngineResult) -> None:
        """Send an EngineResult to all WebSocket clients connected to a game."""
        connections = self._connections.get(game_id, {})
        dead: list[str] = []
        payload = result.model_dump_json()
        for user_id, ws in connections.items():
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(user_id)
        for uid in dead:
            self.disconnect(game_id, uid)

    def get_connected_users(self, game_id: str) -> list[str]:
        return list(self._connections.get(game_id, {}).keys())


# Module-level singleton
ws_manager = ConnectionManager()
