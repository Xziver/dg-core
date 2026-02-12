"""Tests for WebSocket connection management and real-time broadcast."""

import pytest
from starlette.testclient import TestClient

from app.infra.auth import create_access_token
from app.infra.ws_manager import ConnectionManager
from app.models.result import EngineResult


# --- Unit tests for ConnectionManager ---


class TestConnectionManager:
    """Unit tests for the WebSocket ConnectionManager."""

    def test_empty_game_has_no_users(self):
        mgr = ConnectionManager()
        assert mgr.get_connected_users("game1") == []

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_game(self):
        """Broadcasting to a game with no connections should not raise."""
        mgr = ConnectionManager()
        result = EngineResult(success=True, event_type="test")
        await mgr.broadcast_to_game("nonexistent", result)

    def test_disconnect_cleans_up(self):
        mgr = ConnectionManager()
        mgr._connections["g1"]["u1"] = "fake_ws"
        assert mgr.get_connected_users("g1") == ["u1"]
        mgr.disconnect("g1", "u1")
        assert mgr.get_connected_users("g1") == []
        assert "g1" not in mgr._connections

    def test_disconnect_nonexistent_is_noop(self):
        mgr = ConnectionManager()
        mgr.disconnect("no_game", "no_user")  # Should not raise


# --- WebSocket endpoint tests ---


def test_ws_reject_missing_token():
    """WebSocket without token query param should be closed with 4001."""
    from app.main import app

    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/web/ws/game123"):
            pass


def test_ws_reject_invalid_token():
    """WebSocket with invalid JWT should be closed with 4001."""
    from app.main import app

    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/web/ws/game123?token=bad.token.here"):
            pass


def test_ws_connect_valid_token():
    """WebSocket with valid JWT should be accepted and tracked by ws_manager."""
    from app.infra.ws_manager import ws_manager
    from app.main import app

    token_resp = create_access_token("test-user-ws")
    client = TestClient(app)
    with client.websocket_connect(
        f"/api/web/ws/game_ws_test?token={token_resp.access_token}"
    ) as _ws:
        connected = ws_manager.get_connected_users("game_ws_test")
        assert "test-user-ws" in connected

    # After context exit (disconnect), user should be cleaned up
    assert "test-user-ws" not in ws_manager.get_connected_users("game_ws_test")
