"""RAG retrieval interface using ChromaDB."""

from __future__ import annotations

from pydantic import BaseModel

from app.infra.config import settings


class Document(BaseModel):
    content: str
    metadata: dict = {}
    score: float = 0.0


class MockRetriever:
    """Returns empty results when RAG is disabled."""

    async def query(
        self,
        query: str,
        category: str,
        session_id: str | None = None,
        top_k: int = 5,
    ) -> list[Document]:
        return [
            Document(
                content=f"[Mock RAG] 未找到与「{query}」相关的 {category} 类知识。",
                metadata={"category": category, "source": "mock"},
                score=0.0,
            )
        ]


class ChromaRetriever:
    """ChromaDB-backed retriever."""

    def __init__(self) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=settings.rag_persist_dir)

    def _get_collection(self, category: str):  # type: ignore[no-untyped-def]
        return self._client.get_or_create_collection(name=category)

    async def query(
        self,
        query: str,
        category: str,
        session_id: str | None = None,
        top_k: int = 5,
    ) -> list[Document]:
        collection = self._get_collection(category)

        where_filter: dict | None = None
        if session_id:
            where_filter = {"session_id": session_id}

        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter,
        )

        documents: list[Document] = []
        if results and results["documents"]:
            for i, doc_text in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                dist = results["distances"][0][i] if results["distances"] else 0.0
                documents.append(
                    Document(content=doc_text, metadata=meta, score=1.0 - dist)
                )
        return documents


_retriever: MockRetriever | ChromaRetriever | None = None


def get_retriever() -> MockRetriever | ChromaRetriever:
    global _retriever
    if _retriever is None:
        if settings.rag_enabled:
            _retriever = ChromaRetriever()
        else:
            _retriever = MockRetriever()
    return _retriever


async def query_knowledge(
    query: str,
    category: str,
    session_id: str | None = None,
    top_k: int = 5,
) -> list[Document]:
    """Unified RAG query interface."""
    retriever = get_retriever()
    return await retriever.query(query, category, session_id, top_k)
