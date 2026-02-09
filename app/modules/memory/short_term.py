"""Short-term memory — caches recent session events for LLM context."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class MemoryEntry:
    seq: int
    event_type: str
    summary: str


class ShortTermMemory:
    """Per-session ring buffer of recent events."""

    def __init__(self, max_entries: int = 20) -> None:
        self._sessions: dict[str, deque[MemoryEntry]] = {}
        self._max = max_entries

    def _get_buffer(self, session_id: str) -> deque[MemoryEntry]:
        if session_id not in self._sessions:
            self._sessions[session_id] = deque(maxlen=self._max)
        return self._sessions[session_id]

    def add(self, session_id: str, seq: int, event_type: str, summary: str) -> None:
        self._get_buffer(session_id).append(
            MemoryEntry(seq=seq, event_type=event_type, summary=summary)
        )

    def get_recent(self, session_id: str, n: int = 10) -> list[MemoryEntry]:
        buf = self._get_buffer(session_id)
        return list(buf)[-n:]

    def get_context_text(self, session_id: str, n: int = 10) -> str:
        """Return a plain-text summary of recent events for LLM prompts."""
        entries = self.get_recent(session_id, n)
        if not entries:
            return "暂无近期事件。"
        lines = [f"[{e.seq}] {e.event_type}: {e.summary}" for e in entries]
        return "\n".join(lines)

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


short_term_memory = ShortTermMemory()
