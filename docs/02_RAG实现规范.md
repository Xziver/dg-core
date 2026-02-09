# 02 — RAG 实现规范

> 本文档定义 dg-engine 中 RAG（Retrieval-Augmented Generation）模块的架构、
> 知识库组织方式与检索接口规范。

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 世界知识检索 | 为 LLM 叙述提供准确的世界观上下文 |
| 分类管理 | 不同类型知识独立存储，支持精确查询 |
| 可配置 | Embedding 模型与分块策略可通过配置调整 |
| 可 Mock | MVP 阶段可使用 MockRetriever 返回空结果或预设文本 |

---

## 2. 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| 向量数据库 | ChromaDB | 轻量级、内嵌式，适合 MVP 阶段 |
| Embedding | 可配置 | 默认 `sentence-transformers`，支持切换为 OpenAI Embedding API |
| 存储模式 | 本地持久化 | ChromaDB `PersistentClient`，数据存储在 `data/chroma/` |

---

## 3. 知识库分类与 Collection 设计

### 3.1 Collection 分类

每个知识类别对应一个独立的 ChromaDB Collection：

| Collection 名称 | 类别 | 内容说明 | 典型文档 |
|-----------------|------|---------|---------|
| `worldview` | 世界观设定 | 灰山城背景、扇区设定、物理规则 | 世界观文档、设定集 |
| `rulebook` | 规则书 | CMYK 属性规则、战斗规则、通信规则 | 规则手册章节 |
| `module_scripts` | 模组剧本 | DM 编写的具体扇区剧本内容 | 各扇区剧本文件 |
| `game_history` | 游戏历史记录 | 已发生的游戏事件、对话、战斗记录 | timeline_events 归档 |

### 3.2 Metadata Schema

每个 Document 入库时必须携带以下 metadata：

```python
# 通用 metadata 字段
metadata = {
    "category": str,       # 知识类别：worldview / rulebook / module_scripts / game_history
    "source": str,         # 来源文件名或模块名
    "chapter": str,        # 章节 / 扇区标识（如 "sector_1", "chapter_02"）
    "session_id": str,     # 关联的 Session ID（仅 game_history 类别必填，其余可为空）
    "created_at": str,     # 入库时间（ISO 8601 格式）
    "doc_type": str,       # 文档子类型（如 "setting", "npc", "event", "rule"）
}
```

### 3.3 Metadata 过滤示例

```python
# 查询某个 session 的游戏历史
results = collection.query(
    query_texts=["玩家A与NPC的对话"],
    where={"session_id": "sess_abc123"},
    n_results=5,
)

# 查询特定扇区的世界观设定
results = collection.query(
    query_texts=["这个区域的环境描述"],
    where={
        "$and": [
            {"category": "worldview"},
            {"chapter": "sector_2"},
        ]
    },
    n_results=3,
)
```

---

## 4. 文档分块策略（Chunking）

### 4.1 分块参数

```python
# app/infra/config.py（RAG 相关字段）

class Settings(BaseSettings):
    # ChromaDB
    CHROMA_PERSIST_DIR: str = "data/chroma"

    # Chunking
    RAG_CHUNK_SIZE: int = 512          # 每个 chunk 的最大 token 数
    RAG_CHUNK_OVERLAP: int = 64        # chunk 之间的重叠 token 数
    RAG_SEPARATOR: str = "\n\n"        # 优先按段落分割

    # Embedding
    RAG_EMBEDDING_PROVIDER: str = "local"          # local | openai
    RAG_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"  # sentence-transformers 模型名
    RAG_EMBEDDING_API_KEY: str = ""                 # OpenAI Embedding 时使用
```

### 4.2 分块流程

```
原始文档
    ↓
按 RAG_SEPARATOR 分割为段落
    ↓
对每个段落进行 token 计数
    ↓
超过 RAG_CHUNK_SIZE → 按句号/换行符二次分割
    ↓
合并过短的 chunk（< RAG_CHUNK_SIZE / 4）
    ↓
生成最终 chunk 列表（含 overlap）
    ↓
写入 ChromaDB Collection
```

### 4.3 Chunker 接口

```python
# app/modules/rag/chunker.py

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    metadata: dict
    chunk_index: int


def chunk_document(
    text: str,
    metadata: dict,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    separator: str = "\n\n",
) -> list[Chunk]:
    """将文档文本分割为带 metadata 的 chunk 列表"""
    paragraphs = text.split(separator)
    chunks: list[Chunk] = []
    current_text = ""
    index = 0

    for para in paragraphs:
        if len(current_text) + len(para) > chunk_size and current_text:
            chunks.append(Chunk(
                text=current_text.strip(),
                metadata={**metadata, "chunk_index": index},
                chunk_index=index,
            ))
            # 保留 overlap
            overlap_start = max(0, len(current_text) - chunk_overlap)
            current_text = current_text[overlap_start:] + separator + para
            index += 1
        else:
            current_text = current_text + separator + para if current_text else para

    if current_text.strip():
        chunks.append(Chunk(
            text=current_text.strip(),
            metadata={**metadata, "chunk_index": index},
            chunk_index=index,
        ))

    return chunks
```

---

## 5. Embedding 模型配置

### 5.1 Embedding Provider 抽象

```python
# app/modules/rag/embedding.py

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Embedding 供应商抽象"""

    @abstractmethod
    def get_embedding_function(self):
        """返回 ChromaDB 兼容的 EmbeddingFunction"""
        ...


class LocalEmbeddingProvider(EmbeddingProvider):
    """使用 sentence-transformers 本地模型"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name

    def get_embedding_function(self):
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        return SentenceTransformerEmbeddingFunction(model_name=self.model_name)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """使用 OpenAI Embedding API"""

    def __init__(self, api_key: str, model_name: str = "text-embedding-3-small"):
        self.api_key = api_key
        self.model_name = model_name

    def get_embedding_function(self):
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        return OpenAIEmbeddingFunction(
            api_key=self.api_key,
            model_name=self.model_name,
        )
```

### 5.2 工厂函数

```python
def get_embedding_provider() -> EmbeddingProvider:
    from app.infra.config import settings

    if settings.RAG_EMBEDDING_PROVIDER == "local":
        return LocalEmbeddingProvider(model_name=settings.RAG_EMBEDDING_MODEL)
    elif settings.RAG_EMBEDDING_PROVIDER == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.RAG_EMBEDDING_API_KEY,
            model_name=settings.RAG_EMBEDDING_MODEL,
        )
    else:
        raise ValueError(f"未知的 RAG_EMBEDDING_PROVIDER: {settings.RAG_EMBEDDING_PROVIDER}")
```

---

## 6. 检索接口

### 6.1 核心接口定义

```python
# app/modules/rag/retriever.py

from typing import Optional
from dataclasses import dataclass
import chromadb
from app.infra.config import settings
from app.modules.rag.embedding import get_embedding_provider


@dataclass
class RetrievalResult:
    """单条检索结果"""
    text: str
    metadata: dict
    distance: float          # 与查询的距离（越小越相关）


# ChromaDB 客户端（单例）
_chroma_client: Optional[chromadb.ClientAPI] = None


def get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR
        )
    return _chroma_client


async def query_knowledge(
    query: str,
    category: str,
    session_id: Optional[str] = None,
    top_k: int = 5,
) -> list[RetrievalResult]:
    """
    统一知识检索接口。

    参数:
        query:      查询文本
        category:   知识类别（worldview / rulebook / module_scripts / game_history）
        session_id: Session ID（仅 game_history 时有效，用于过滤）
        top_k:      返回结果数量

    返回:
        按相关度排序的检索结果列表
    """
    client = get_chroma_client()
    embedding_fn = get_embedding_provider().get_embedding_function()

    collection = client.get_or_create_collection(
        name=category,
        embedding_function=embedding_fn,
    )

    # 构建过滤条件
    where_filter = None
    if session_id and category == "game_history":
        where_filter = {"session_id": session_id}

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where_filter,
    )

    retrieval_results = []
    if results and results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            retrieval_results.append(RetrievalResult(
                text=doc,
                metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                distance=results["distances"][0][i] if results["distances"] else 0.0,
            ))

    return retrieval_results
```

### 6.2 使用示例

```python
# 在 domain/rules/narration.py 中使用

from app.modules.rag.retriever import query_knowledge
from app.modules.llm.client import ask_llm
from app.modules.llm.prompts import SCENE_DESCRIPTION, SYSTEM_NARRATOR


async def generate_scene_description(sector_name: str, area_name: str, world_state: dict) -> str:
    # 1. 检索相关世界设定
    rag_results = await query_knowledge(
        query=f"{sector_name} {area_name} 环境描述",
        category="worldview",
        top_k=3,
    )
    rag_context = "\n---\n".join([r.text for r in rag_results])

    # 2. 构建 prompt 并调用 LLM
    prompt = SCENE_DESCRIPTION.substitute(
        sector_name=sector_name,
        area_name=area_name,
        environment=world_state.get("environment", "未知"),
        world_state=str(world_state),
        rag_context=rag_context,
    )
    return await ask_llm(prompt=prompt, system_message=SYSTEM_NARRATOR)
```

---

## 7. 文档入库接口

### 7.1 Index 接口

```python
# app/modules/rag/index.py

from typing import Optional
from app.modules.rag.retriever import get_chroma_client
from app.modules.rag.embedding import get_embedding_provider
from app.modules.rag.chunker import chunk_document, Chunk
import uuid


async def index_document(
    text: str,
    category: str,
    source: str,
    chapter: str = "",
    session_id: str = "",
    doc_type: str = "general",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> int:
    """
    将文档分块后写入对应 Collection。

    参数:
        text:        原始文档文本
        category:    知识类别（即 Collection 名称）
        source:      来源标识
        chapter:     章节 / 扇区标识
        session_id:  关联 Session ID
        doc_type:    文档子类型
        chunk_size:  分块大小
        chunk_overlap: 分块重叠

    返回:
        写入的 chunk 数量
    """
    from datetime import datetime, timezone

    metadata_base = {
        "category": category,
        "source": source,
        "chapter": chapter,
        "session_id": session_id,
        "doc_type": doc_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    chunks = chunk_document(
        text=text,
        metadata=metadata_base,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    client = get_chroma_client()
    embedding_fn = get_embedding_provider().get_embedding_function()
    collection = client.get_or_create_collection(
        name=category,
        embedding_function=embedding_fn,
    )

    # 批量写入
    collection.add(
        ids=[f"{source}_{c.chunk_index}_{uuid.uuid4().hex[:8]}" for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[c.metadata for c in chunks],
    )

    return len(chunks)


async def index_game_event(
    session_id: str,
    event_text: str,
    event_type: str,
    chapter: str = "",
) -> int:
    """将单条游戏事件写入 game_history Collection（不分块）"""
    return await index_document(
        text=event_text,
        category="game_history",
        source=f"session_{session_id}",
        chapter=chapter,
        session_id=session_id,
        doc_type=event_type,
        chunk_size=9999,  # 单条事件不分块
    )
```

---

## 8. Mock Retriever

MVP 阶段可使用 Mock 实现，跳过 ChromaDB 依赖：

```python
# app/modules/rag/mock_retriever.py

from typing import Optional
from app.modules.rag.retriever import RetrievalResult


async def query_knowledge_mock(
    query: str,
    category: str,
    session_id: Optional[str] = None,
    top_k: int = 5,
) -> list[RetrievalResult]:
    """Mock 检索接口，返回空结果或预设文本"""
    return [
        RetrievalResult(
            text=f"[MOCK] {category} 类别的模拟知识片段",
            metadata={"category": category, "source": "mock"},
            distance=0.0,
        )
    ]
```

通过配置切换：

```python
# app/infra/config.py

class Settings(BaseSettings):
    RAG_ENABLED: bool = False  # MVP 阶段默认关闭

# app/modules/rag/retriever.py 中判断
async def query_knowledge(...) -> list[RetrievalResult]:
    if not settings.RAG_ENABLED:
        from app.modules.rag.mock_retriever import query_knowledge_mock
        return await query_knowledge_mock(query, category, session_id, top_k)
    # ... 正常检索逻辑
```

---

## 9. 调用约束

### 9.1 调用链路

```
domain.rules.*
    ├── modules.rag.retriever.query_knowledge()   ← 检索知识
    └── modules.llm.client.ask_llm()              ← 结合检索结果生成叙述
```

### 9.2 禁止事项

| 禁止行为 | 原因 |
|----------|------|
| 在 `api/` 层直接调用 `query_knowledge` | 违反分层架构 |
| 在 RAG 检索结果中提取结构化数据用于游戏判定 | RAG 仅提供叙述上下文 |
| 跨 Collection 混合查询 | 保持知识类别隔离，避免干扰 |

### 9.3 数据生命周期

| Collection | 写入时机 | 清理策略 |
|-----------|---------|---------|
| `worldview` | 项目初始化 / 世界观更新时 | 手动管理，版本化 |
| `rulebook` | 规则更新时 | 手动管理，版本化 |
| `module_scripts` | DM 上传剧本时 | 按扇区 / 章节管理 |
| `game_history` | 每个游戏事件结算后 | 按 session_id 归档，Session 结束后可选清理 |

---

## 10. 测试策略

```python
# tests/modules/rag/test_retriever.py

import pytest
from app.modules.rag.retriever import query_knowledge


@pytest.mark.asyncio
async def test_query_knowledge_mock(monkeypatch):
    """Mock 模式下应返回预设结果"""
    monkeypatch.setattr("app.infra.config.settings.RAG_ENABLED", False)
    results = await query_knowledge(
        query="灰山城的历史",
        category="worldview",
    )
    assert len(results) > 0
    assert results[0].metadata["source"] == "mock"


@pytest.mark.asyncio
async def test_query_knowledge_with_session_filter(monkeypatch):
    """game_history 查询应携带 session_id 过滤"""
    monkeypatch.setattr("app.infra.config.settings.RAG_ENABLED", False)
    results = await query_knowledge(
        query="战斗记录",
        category="game_history",
        session_id="sess_001",
    )
    assert isinstance(results, list)
```
