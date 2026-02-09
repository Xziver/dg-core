# dg-core

**Digital Ghost (电子幽灵)** — TRPG 世界引擎服务

灰山城数字世界的后端引擎。接收结构化事件，执行游戏规则（CMYK 属性、骰子检定、战斗），返回结构化结果 + LLM 叙述文本。

## 快速开始

```bash
# 安装依赖
uv sync --extra dev

# 运行测试（15 个，内存 SQLite，无需外部服务）
pytest -v

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后：
- Swagger 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health` → `{"status": "ok", "engine": "dg-core", "version": "0.1.0"}`

## 项目结构

```
dg-core/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── api/                  # HTTP 路由
│   │   ├── admin.py          # 管理 API (Player/Session/Character CRUD)
│   │   ├── bot.py            # 游戏 API (事件提交 + 查询)
│   │   └── web.py            # WebSocket (预留)
│   ├── domain/               # 核心领域逻辑
│   │   ├── dispatcher.py     # 事件分发器（唯一入口）
│   │   ├── session.py        # 会话管理
│   │   ├── character.py      # 角色管理 + CMYK helpers
│   │   ├── timeline.py       # 时间线
│   │   ├── world.py          # 世界状态
│   │   ├── context.py        # LLM 上下文组装
│   │   └── rules/            # 游戏规则
│   │       ├── skill.py      # 技能检定
│   │       ├── combat.py     # 战斗流程
│   │       └── narration.py  # LLM 叙述生成
│   ├── models/               # 数据模型
│   │   ├── db_models.py      # 9 个 ORM 表
│   │   ├── event.py          # 17 种事件 (discriminated union)
│   │   └── result.py         # EngineResult
│   ├── modules/              # 可插拔模块
│   │   ├── llm/              # LLM (OpenAI/Anthropic/Mock)
│   │   ├── rag/              # RAG 向量检索 (ChromaDB/Mock)
│   │   ├── dice/             # CMYK 骰子系统
│   │   └── memory/           # 短期记忆 (ring buffer)
│   └── infra/                # 基础设施
│       ├── config.py         # Pydantic Settings
│       ├── db.py             # 异步数据库连接
│       └── cache.py          # 内存缓存
├── tests/                    # 测试 (15 个)
├── alembic/                  # 数据库迁移
├── docs/                     # 规范文档
├── pyproject.toml
└── .env.example
```

## 配置

复制 `.env.example` 为 `.env`：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./dg_core.db` | 数据库连接串 |
| `LLM_PROVIDER` | `mock` | `mock` / `openai` / `anthropic` |
| `LLM_API_KEY` | _(空)_ | LLM API 密钥 |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容 API 地址 |
| `LLM_MODEL` | `gpt-4o-mini` | 模型名称 |
| `RAG_ENABLED` | `false` | 是否启用 ChromaDB |
| `DEFAULT_DICE_TYPE` | `6` | 骰子面数 |
| `APP_DEBUG` | `true` | 调试模式 |

**开发阶段保持默认即可**，不需要任何 API Key。

## API 概览

### 管理接口 `/api/admin/*`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/players` | 创建玩家 |
| POST | `/api/admin/sessions` | 创建会话 |
| PUT | `/api/admin/sessions/{id}` | 更新会话 |
| POST | `/api/admin/sessions/{id}/players` | 添加玩家到会话 |
| POST | `/api/admin/characters/patient` | 创建褪色症患者 |
| POST | `/api/admin/characters/ghost` | 创建电子幽灵 |
| GET | `/api/admin/characters/{id}` | 查询角色 |
| POST | `/api/admin/rag/upload` | 上传 RAG 文档 |

### 游戏接口 `/api/bot/*`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bot/events` | 提交游戏事件（核心接口） |
| GET | `/api/bot/sessions/{id}` | 查询会话信息 |
| GET | `/api/bot/sessions/{id}/state` | 查询世界状态 |
| GET | `/api/bot/sessions/{id}/timeline` | 查询事件时间线 |

### 事件类型

通过 `POST /api/bot/events` 提交，`payload.event_type` 决定类型：

| 分类 | event_type | 说明 |
|------|------------|------|
| 系统 | `session_start` / `session_end` | 会话控制 |
| 系统 | `player_join` / `player_leave` | 玩家进出 |
| 行动 | `skill_check` | CMYK 技能检定 |
| 行动 | `explore` | 探索区域 |
| 战斗 | `attack` / `defend` | 攻击 / 防御 |
| 战斗 | `use_print_ability` / `reroll` | 使用能力 / 重投 |
| 通信 | `initiate_comm` / `download_ability` / `deep_scan` / `attempt_seize` | 玩家间数据交换 |
| 状态 | `apply_fragment` / `hp_change` / `sector_transition` | 状态变更 |

## 测试

```bash
pytest                       # 全部 15 个测试
pytest tests/test_dice.py    # 骰子单元测试 (8)
pytest tests/test_api.py     # API 集成测试 (6)
pytest tests/test_e2e.py     # 端到端场景测试 (1)
```

测试使用内存 SQLite + MockProvider，无需外部依赖。

## 数据库迁移

```bash
alembic upgrade head                          # 执行迁移
alembic revision --autogenerate -m "desc"     # 生成迁移
alembic downgrade -1                          # 回退一步
```

## 技术栈

Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Pydantic 2.0 / Alembic / ChromaDB / httpx / pytest
