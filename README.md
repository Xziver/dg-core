# dg-core

**Digital Ghost (电子幽灵)** — TRPG 世界引擎服务

灰山城数字世界的后端引擎。接收结构化事件，执行游戏规则（CMYK 属性、骰子检定、战斗），返回结构化结果 + LLM 叙述文本。支持多平台用户认证（QQ/Discord/Web）和 WebSocket 实时同步。

## 快速开始

```bash
# 安装依赖
uv sync --extra dev

# 运行测试（45 个，内存 SQLite，无需外部服务）
pytest -v

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后：
- Swagger 文档：`http://localhost:8000/docs`
- 管理后台：`http://localhost:8000/admin/`
- 健康检查：`http://localhost:8000/health` → `{"status": "ok", "engine": "dg-core", "version": "0.1.0"}`

## 项目结构

```
dg-core/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── api/                  # HTTP 路由
│   │   ├── auth.py           # 认证 API (注册/登录/绑定平台)
│   │   ├── admin.py          # 管理 API (Game/Region/Character CRUD)
│   │   ├── bot.py            # 游戏 API (事件提交 + 查询)
│   │   └── web.py            # WebSocket 实时推送
│   ├── admin/                 # 管理后台 (sqladmin)
│   │   ├── auth.py            # 管理员认证 (API Key + role=admin)
│   │   ├── views/             # 12 个 ORM 模型的 CRUD 视图
│   │   └── custom/            # 自定义视图 (仪表盘/CMYK编辑器/批量导入)
│   ├── templates/admin/       # 自定义 Jinja2 模板
│   ├── domain/               # 核心领域逻辑
│   │   ├── dispatcher.py     # 事件分发器（唯一入口）
│   │   ├── game.py           # 游戏管理 (Game 生命周期 + flags)
│   │   ├── session.py        # 跑团活动管理 (Session 生命周期)
│   │   ├── region.py         # 地区/地点管理 + 玩家位置
│   │   ├── character.py      # 角色管理 + CMYK helpers
│   │   ├── timeline.py       # 时间线
│   │   ├── context.py        # LLM 上下文组装
│   │   └── rules/            # 游戏规则
│   │       ├── skill.py      # 技能检定
│   │       ├── combat.py     # 战斗流程
│   │       └── narration.py  # LLM 叙述生成
│   ├── models/               # 数据模型
│   │   ├── db_models.py      # 12 个 ORM 表
│   │   ├── event.py          # 19 种事件 (discriminated union)
│   │   └── result.py         # EngineResult
│   ├── modules/              # 可插拔模块
│   │   ├── llm/              # LLM (OpenAI/Anthropic/Mock)
│   │   ├── rag/              # RAG 向量检索 (ChromaDB/Mock)
│   │   ├── dice/             # CMYK 骰子系统
│   │   └── memory/           # 短期记忆 (ring buffer)
│   └── infra/                # 基础设施
│       ├── config.py         # Pydantic Settings
│       ├── db.py             # 异步数据库连接
│       ├── auth.py           # JWT + API Key 认证
│       ├── ws_manager.py     # WebSocket 连接管理 + 广播
│       └── cache.py          # 内存缓存
├── tests/                    # 测试 (45 个)
├── scripts/                  # 管理脚本 (promote_admin.py)
├── alembic/                  # 数据库迁移
├── docs/                     # 规范文档
├── pyproject.toml
└── .env.example
```

## 数据模型层级

```
User (独立账号, 支持多平台绑定)
  ├── PlatformBinding[] (qq, discord, web...)
  ├──(N:M)── GamePlayer ──(N:M)── Game (一局游戏)
  │              ├─ current_region ──────├── Region[] (A/B/C/D)
  │              └─ current_location ───►│     └── Location[]
  │                                      │
  └── Patient[] ──(game_id FK)──────────►├── Patient[] ──(1:1)── Ghost
                                         │                        ├── PrintAbility[]
                                         │                        └── ColorFragment[]
                                         │
                                         └── Session[] (单次跑团活动)
                                               └── TimelineEvent[]
```

## 认证系统

支持三种认证方式，所有接口（除 `/health` 和 `/api/auth/*`）均需认证：

| 认证方式 | Header | 适用场景 |
|---------|--------|---------|
| JWT Bearer | `Authorization: Bearer <token>` | Web 客户端 |
| API Key | `X-API-Key: <64字符hex>` | Bot 服务 |
| JWT Query Param | `?token=<jwt>` | WebSocket 连接 |

### 认证流程

```
首次使用:    POST /api/auth/register        → 获得 user_id + api_key + access_token
QQ Bot登录:  POST /api/auth/login/platform   → QQ uid 解析为 JWT
Web登录:     POST /api/auth/login/api-key    → API Key 换取 JWT
绑定平台:    POST /api/auth/bind-platform    → 同一用户绑定多个平台
查看信息:    GET  /api/auth/me               → 用户信息 + 所有平台绑定
```

### 实时同步

QQ Bot 提交事件 → 引擎处理 → WebSocket 广播给所有在线 Web 客户端：

```
QQ群: /attack ──► Bot ──► POST /api/bot/events ──► dispatcher
                                                        │
                              HTTP响应 ◄────────────────┤
                              (Bot转发到QQ群)            │
                                                        ▼
                                              ws_manager.broadcast_to_game()
                                                        │
                              Web客户端 ◄── WebSocket ──┘
                              (实时显示HP变化)
```

Web 客户端连接：`ws://host/api/web/ws/{game_id}?token=<jwt>`

## 管理后台

基于 [sqladmin](https://github.com/aminalaee/sqladmin) 的 Django 风格管理界面，无需直接操作数据库。

### 设置管理员

```bash
# 1. 注册用户
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Admin", "platform": "web", "platform_uid": "admin"}'
# 记下返回的 user_id

# 2. 提升为管理员
python scripts/promote_admin.py <user_id>
```

### 登录

访问 `http://localhost:8000/admin/login`，用户名任意填写，密码填写注册时返回的 **API Key**。

### 功能

| 页面 | URL | 说明 |
|------|-----|------|
| 模型管理 | `/admin/` | 所有 12 个 ORM 模型的列表/详情/创建/编辑/删除 |
| 仪表盘 | `/admin/dashboard` | 游戏状态总览（用户数、游戏数、活跃会话等） |
| CMYK 编辑器 | `/admin/cmyk-editor` | 可视化滑块编辑 Ghost 的 CMYK 属性，实时颜色预览 |
| 批量操作 | `/admin/bulk` | CSV 导入/导出地区、地点、患者、幽灵数据 |

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
| `JWT_SECRET_KEY` | `dev-secret-change-in-production` | JWT 签名密钥 |
| `JWT_ALGORITHM` | `HS256` | JWT 算法 |
| `JWT_EXPIRE_MINUTES` | `1440` | JWT 过期时间（24小时） |

**开发阶段保持默认即可**，不需要任何 API Key。

## API 概览

### 认证接口 `/api/auth/*`（无需认证）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册用户（返回 user_id + api_key + JWT） |
| POST | `/api/auth/login/platform` | 平台登录（QQ/Discord uid → JWT） |
| POST | `/api/auth/login/api-key` | API Key 登录（→ JWT） |
| POST | `/api/auth/bind-platform` | 绑定新平台（需 JWT） |
| GET | `/api/auth/me` | 查看用户信息（需 JWT） |

### 管理接口 `/api/admin/*`（需认证）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/games` | 创建游戏 |
| PUT | `/api/admin/games/{id}` | 更新游戏 |
| POST | `/api/admin/games/{id}/players` | 添加玩家到游戏 |
| POST | `/api/admin/games/{id}/regions` | 创建地区 |
| GET | `/api/admin/games/{id}/regions` | 查询地区列表 |
| POST | `/api/admin/regions/{id}/locations` | 创建地点 |
| GET | `/api/admin/regions/{id}/locations` | 查询地点列表 |
| POST | `/api/admin/characters/patient` | 创建褪色症患者 |
| POST | `/api/admin/characters/ghost` | 创建电子幽灵 |
| GET | `/api/admin/characters/{id}` | 查询角色 |
| POST | `/api/admin/rag/upload` | 上传 RAG 文档 |

### 游戏接口 `/api/bot/*`（需认证）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bot/events` | 提交游戏事件（核心接口） |
| GET | `/api/bot/games/{id}` | 查询游戏信息 |
| GET | `/api/bot/sessions/{id}/timeline` | 查询活动时间线 |
| GET | `/api/bot/games/{id}/timeline` | 查询游戏全局时间线 |

### WebSocket `/api/web/*`

| 路径 | 说明 |
|------|------|
| `WS /api/web/ws/{game_id}?token=<jwt>` | 实时游戏事件推送 |
| `GET /api/web/health` | Web API 健康检查 |

### 事件类型

通过 `POST /api/bot/events` 提交，`payload.event_type` 决定类型：

| 分类 | event_type | 说明 |
|------|------------|------|
| 游戏生命周期 | `game_start` / `game_end` | 游戏控制 |
| 游戏生命周期 | `player_join` / `player_leave` | 玩家进出 |
| 跑团活动 | `session_start` / `session_end` | 跑团活动控制 |
| 行动 | `skill_check` | CMYK 技能检定 |
| 行动 | `explore` | 探索区域 |
| 战斗 | `attack` / `defend` | 攻击 / 防御 |
| 战斗 | `use_print_ability` | 使用能力 |
| 通信 | `initiate_comm` / `download_ability` / `deep_scan` / `attempt_seize` | 玩家间数据交换 |
| 状态 | `apply_fragment` / `hp_change` | 属性变更 |
| 状态 | `region_transition` / `location_transition` | 位置移动 |

## 测试

```bash
pytest                          # 全部 45 个测试
pytest tests/test_dice.py       # 骰子单元测试 (8)
pytest tests/test_api.py        # API 集成测试 (8)
pytest tests/test_auth.py       # 认证测试 (12)
pytest tests/test_websocket.py  # WebSocket 测试 (7)
pytest tests/test_admin_dashboard.py  # 管理后台测试 (9)
pytest tests/test_e2e.py        # 端到端场景测试 (1)
```

测试使用内存 SQLite + MockProvider，无需外部依赖。

## 数据库迁移

```bash
alembic upgrade head                          # 执行迁移
alembic revision --autogenerate -m "desc"     # 生成迁移
alembic downgrade -1                          # 回退一步
```

## 技术栈

Python 3.12 / FastAPI / SQLAlchemy 2.0 async / sqladmin / Pydantic 2.0 / python-jose (JWT) / Alembic / ChromaDB / httpx / WebSocket / pytest
