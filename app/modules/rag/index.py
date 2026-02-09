"""RAG knowledge index management."""

from __future__ import annotations

from app.infra.config import settings

COLLECTIONS = ["world_setting", "rulebook", "module_script", "game_history"]


def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """Split text into overlapping chunks."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


async def index_document(
    content: str,
    category: str,
    metadata: dict | None = None,
) -> int:
    """Index a document into the specified collection. Returns number of chunks stored."""
    if not settings.rag_enabled:
        return 0

    import chromadb

    client = chromadb.PersistentClient(path=settings.rag_persist_dir)
    collection = client.get_or_create_collection(name=category)

    chunks = _chunk_text(content)
    meta = metadata or {}

    ids = [f"{category}_{collection.count() + i}" for i in range(len(chunks))]
    metadatas = [meta] * len(chunks)

    collection.add(documents=chunks, ids=ids, metadatas=metadatas)
    return len(chunks)


async def index_game_event(
    session_id: str,
    event_summary: str,
    metadata: dict | None = None,
) -> None:
    """Index a single game event into the game_history collection."""
    meta = {"session_id": session_id, **(metadata or {})}
    await index_document(event_summary, "game_history", meta)
