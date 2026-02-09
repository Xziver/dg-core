# dg-engine 使用文档

## 目录

- [环境准备](#环境准备)
- [项目结构](#项目结构)
- [配置说明](#配置说明)
- [启动服务](#启动服务)
- [API 参考](#api-参考)
  - [健康检查](#健康检查)
  - [管理接口 Admin](#管理接口-admin)
  - [游戏接口 Bot](#游戏接口-bot)
- [事件类型一览](#事件类型一览)
- [引擎返回结构](#引擎返回结构)
- [完整游戏流程示例](#完整游戏流程示例)
- [测试](#测试)
- [数据库迁移](#数据库迁移)

---

## 环境准备

本项目使用 [uv](https://docs.astral.sh/uv/) 管理依赖。

```bash
# 安装依赖（含开发工具）
uv sync --extra dev

# 仅安装运行时依赖
uv sync

# 生产环境（PostgreSQL 驱动）
uv sync --extra prod
```

## 项目结构

```
dg-core/
├── pyproject.toml          # 项目配置 & 依赖
├── uv.lock                 # 锁定文件
├── .env.example            # 环境变量模板
├── alembic.ini             # 数据库迁移配置
├── alembic/                # 迁移脚本
├── app/
│   ├── main.py             # FastAPI 入口
│   ├── api/                # HTTP 接口
│   │   ├── admin.py        # 管理 API
│   │   ├── bot.py          # 游戏 API
│   │   └── web.py          # 预留（未实现）
│   ├── domain/             # 核心领域逻辑
│   │   ├── dispatcher.py   # 事件分发器（唯一入口）
│   │   ├── session.py      # 会话管理
│   │   ├── character.py    # 角色管理
│   │   ├── timeline.py     # 时间线
│   │   ├── world.py        # 世界状态
│   │   ├── context.py      # LLM 上下文组装
│   │   └── rules/          # 游戏规则
│   │       ├── skill.py    # 技能检定
│   │       ├── combat.py   # 战斗流程
│   │       └── narration.py# 叙述生成
│   ├── models/             # 数据模型
│   │   ├── db_models.py    # ORM 表定义
│   │   ├── event.py        # 事件 Schema
│   │   └── result.py       # 结果 Schema
│   ├── modules/            # 可插拔能力模块
│   │   ├── llm/            # LLM 抽象层
│   │   ├── rag/            # RAG 检索
│   │   ├── dice/           # CMYK 骰子
│   │   └── memory/         # 短期记忆
│   └── infra/              # 基础设施
│       ├── config.py       # 配置读取
│       ├── db.py           # 数据库连接
│       └── cache.py        # 内存缓存
├── tests/                  # 测试
│   ├── conftest.py         # 公共 fixture
│   ├── test_dice.py        # 骰子单元测试
│   ├── test_api.py         # API 集成测试
│   └── test_e2e.py         # 端到端场景测试
└── docs/                   # 设计文档
```

## 配置说明

复制 `.env.example` 为 `.env`，按需修改：

```bash
cp .env.example .env
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./dg_engine.db` | 数据库连接串。生产环境用 `postgresql+asyncpg://...` |
| `LLM_PROVIDER` | `mock` | LLM 后端：`mock` / `openai` / `anthropic` |
| `LLM_API_KEY` | _(空)_ | LLM API 密钥 |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容 API 地址（可指向其他服务） |
| `LLM_MODEL` | `gpt-4o-mini` | 模型名称 |
| `RAG_ENABLED` | `false` | 是否启用 ChromaDB RAG |
| `RAG_PERSIST_DIR` | `./chroma_data` | ChromaDB 持久化目录 |
| `DEFAULT_DICE_TYPE` | `6` | 骰子面数（d6 / d10 / d20） |
| `APP_HOST` | `0.0.0.0` | 监听地址 |
| `APP_PORT` | `8000` | 监听端口 |
| `APP_DEBUG` | `true` | 调试模式（开启 SQL echo） |

## 启动服务

```bash
# 开发模式（自动重载）
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

启动后访问：
- API 文档（Swagger）：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

---

## API 参考

### 健康检查

```
GET /health
```

```json
{"status": "ok", "engine": "dg-engine", "version": "0.1.0"}
```

---

### 管理接口 Admin

#### 创建玩家

```
POST /api/admin/players
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `platform` | string | 是 | 平台标识：`discord` / `qq` / `web` |
| `platform_uid` | string | 是 | 平台用户 ID |
| `display_name` | string | 是 | 显示名 |

返回：

```json
{
  "player_id": "a1b2c3d4...",
  "api_key": "64位hex密钥（仅返回一次，请妥善保存）"
}
```

#### 创建会话

```
POST /api/admin/sessions
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 会话名称 |
| `created_by` | string | 是 | 创建者 player_id（自动以 KP 身份加入） |
| `config` | object | 否 | 自定义配置（如 `{"dice_type": 10}`） |

返回：

```json
{"session_id": "...", "name": "灰山城第一章", "status": "preparing"}
```

#### 更新会话

```
PUT /api/admin/sessions/{session_id}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 否 | 新名称 |
| `status` | string | 否 | 新状态：`preparing` / `active` / `paused` / `ended` |
| `config` | object | 否 | 新配置 |

#### 添加玩家到会话

```
POST /api/admin/sessions/{session_id}/players
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `player_id` | string | 是 | | 玩家 ID |
| `role` | string | 否 | `"PL"` | 角色：`KP`（主持人）/ `PL`（玩家） |

#### 创建患者（褪色症患者）

```
POST /api/admin/characters/patient
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `player_id` | string | 是 | 所属玩家 |
| `session_id` | string | 是 | 所属会话 |
| `name` | string | 是 | 角色名 |
| `soul_color` | string | 是 | 灵魂底色：`C` / `M` / `Y` / `K` |
| `gender` | string | 否 | 性别 |
| `age` | int | 否 | 年龄 |
| `identity` | string | 否 | 原社会身份 |
| `portrait_url` | string | 否 | 立绘 URL |
| `personality_archives` | object | 否 | 四色人格档案 `{"C": "...", "M": "...", "Y": "...", "K": "..."}` |
| `ideal_projection` | string | 否 | 理想投射（第一人称描述） |

返回中包含自动生成的 SWAP 文件：

```json
{
  "patient_id": "...",
  "name": "林默",
  "swap_file": {
    "type": "SWAP",
    "soul_color": "C",
    "ideal_projection": "我想成为...",
    "revealed_archive": {"C": "仅底色对应的档案"}
  }
}
```

#### 创建幽灵（电子幽灵）

```
POST /api/admin/characters/ghost
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `patient_id` | string | 是 | | 绑定的患者 ID |
| `creator_player_id` | string | 是 | | 创建者玩家 ID（不同于患者本人） |
| `session_id` | string | 是 | | 所属会话 |
| `name` | string | 是 | | 幽灵名 |
| `soul_color` | string | 是 | | 底色，初始该色值为 1，其余为 0 |
| `appearance` | string | 否 | | 外观描述 |
| `personality` | string | 否 | | 性格描述 |
| `initial_hp` | int | 否 | `10` | 初始 HP（量子活性） |
| `print_abilities` | array | 否 | | 打印能力列表（见下） |

打印能力对象：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `name` | string | 是 | | 能力名称 |
| `color` | string | 是 | | 关联颜色 |
| `description` | string | 否 | | 能力描述 |
| `ability_count` | int | 否 | `1` | 可用次数 |

返回：

```json
{
  "ghost_id": "...",
  "name": "Echo",
  "cmyk": {"C": 1, "M": 0, "Y": 0, "K": 0},
  "hp": 10,
  "hp_max": 10,
  "print_abilities": [
    {"id": "...", "name": "数据逆流", "color": "C"}
  ]
}
```

#### 查询角色

```
GET /api/admin/characters/{character_id}
```

自动识别类型（ghost 或 patient），返回对应数据。

#### 上传 RAG 知识文档

```
POST /api/admin/rag/upload
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | string | 是 | 文档内容 |
| `category` | string | 是 | 分类：`world_setting` / `rulebook` / `module_script` / `game_history` |
| `metadata` | object | 否 | 附加元数据 |

> 需 `RAG_ENABLED=true` 才会实际写入 ChromaDB。

---

### 游戏接口 Bot

#### 提交游戏事件（核心接口）

```
POST /api/bot/events
```

请求体结构：

```json
{
  "session_id": "会话ID",
  "player_id": "玩家ID",
  "payload": {
    "event_type": "事件类型",
    ...事件参数
  }
}
```

`payload` 通过 `event_type` 字段自动识别类型（discriminated union），具体参见下方 [事件类型一览](#事件类型一览)。

#### 查询会话信息

```
GET /api/bot/sessions/{session_id}
```

```json
{
  "session_id": "...",
  "name": "灰山城第一章",
  "status": "active",
  "config": {"dice_type": 6},
  "players": [
    {"player_id": "...", "role": "KP"},
    {"player_id": "...", "role": "PL"}
  ]
}
```

#### 查询世界状态

```
GET /api/bot/sessions/{session_id}/state
```

```json
{
  "session_id": "...",
  "current_sector": "信号裂痕",
  "sector_data": null,
  "global_flags": {}
}
```

#### 查询时间线

```
GET /api/bot/sessions/{session_id}/timeline?limit=50&offset=0
```

```json
{
  "session_id": "...",
  "events": [
    {
      "id": "...",
      "seq": 1,
      "event_type": "session_start",
      "actor_id": "...",
      "data": null,
      "result": null,
      "narrative": null,
      "created_at": "2026-02-09T12:00:00+00:00"
    }
  ]
}
```

---

## 事件类型一览

所有事件通过 `POST /api/bot/events` 提交，`payload.event_type` 决定类型。

### 系统事件

| event_type | 参数 | 说明 |
|------------|------|------|
| `session_start` | _(无)_ | 开始会话（状态 → active） |
| `session_end` | _(无)_ | 结束会话（状态 → ended） |
| `player_join` | `role`: KP/PL（默认 PL） | 玩家加入会话 |
| `player_leave` | _(无)_ | 玩家离开会话 |

### 行动事件

| event_type | 参数 | 说明 |
|------------|------|------|
| `skill_check` | `color`: C/M/Y/K, `difficulty`: int, `context`: string | CMYK 技能检定 |
| `explore` | `target_area`: string | 探索区域 |

### 战斗事件

| event_type | 参数 | 说明 |
|------------|------|------|
| `attack` | `attacker_ghost_id`, `target_ghost_id`, `color_used` | 攻击，自动投骰 + 伤害 + 碎片掉落 |
| `defend` | `defender_ghost_id`, `color_used` | 防御 |
| `use_print_ability` | `ghost_id`, `ability_id`, `target_roll_id`(可选) | 使用打印能力（消耗次数） |

### 通信事件

| event_type | 参数 | 说明 |
|------------|------|------|
| `initiate_comm` | `initiator_ghost_id`, `target_ghost_id` | 发起通信 |
| `download_ability` | `from_ghost_id`, `ability_id` | 下载对方打印能力 |
| `deep_scan` | `target_patient_id` | 深层扫描（查看保密层） |
| `attempt_seize` | `target_ghost_id` | 尝试夺取幽灵 |

### 状态事件

| event_type | 参数 | 说明 |
|------------|------|------|
| `apply_fragment` | `ghost_id`, `color`, `value`(默认 1) | 应用颜色碎片（提升 CMYK） |
| `hp_change` | `ghost_id`, `delta`, `reason` | HP 变动（正数回复，负数伤害） |
| `sector_transition` | `target_sector` | 扇区转换 |

---

## 引擎返回结构

所有事件处理后返回统一的 `EngineResult`：

```json
{
  "success": true,
  "event_type": "skill_check",
  "data": {
    "ghost_id": "...",
    "color": "C",
    "roll_total": 4,
    "difficulty": 3,
    "check_success": true,
    "dice_results": [2, 2]
  },
  "narrative": "数据流中闪过一道蓝光...",
  "state_changes": [
    {
      "entity_type": "ghost",
      "entity_id": "...",
      "field": "cmyk.C",
      "old_value": "1",
      "new_value": "2"
    }
  ],
  "rolls": [
    {
      "dice_count": 1,
      "dice_type": 6,
      "results": [4],
      "total": 4,
      "difficulty": 3,
      "success": true,
      "rerolled": false,
      "reroll_results": null
    }
  ],
  "error": null
}
```

---

## 完整游戏流程示例

以下使用 `curl` 演示一次完整的游戏流程。

### 1. 创建玩家

```bash
# KP（主持人）
curl -s -X POST http://localhost:8000/api/admin/players \
  -H "Content-Type: application/json" \
  -d '{"platform": "discord", "platform_uid": "kp001", "display_name": "KP小倩"}'
# → 记录 player_id 为 $KP_ID

# PL（玩家A）
curl -s -X POST http://localhost:8000/api/admin/players \
  -H "Content-Type: application/json" \
  -d '{"platform": "discord", "platform_uid": "pl001", "display_name": "玩家A"}'
# → 记录 player_id 为 $PL_ID

# PL（玩家B，负责为玩家A创建幽灵）
curl -s -X POST http://localhost:8000/api/admin/players \
  -H "Content-Type: application/json" \
  -d '{"platform": "discord", "platform_uid": "pl002", "display_name": "玩家B"}'
# → 记录 player_id 为 $PL2_ID
```

### 2. 创建会话 & 玩家加入

```bash
# KP 创建会话（自动以 KP 身份加入）
curl -s -X POST http://localhost:8000/api/admin/sessions \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"灰山城第一章·信号裂痕\", \"created_by\": \"$KP_ID\"}"
# → 记录 session_id 为 $SESSION_ID

# 玩家A 加入
curl -s -X POST http://localhost:8000/api/admin/sessions/$SESSION_ID/players \
  -H "Content-Type: application/json" \
  -d "{\"player_id\": \"$PL_ID\", \"role\": \"PL\"}"
```

### 3. 创建角色

```bash
# 玩家A 创建患者档案
curl -s -X POST http://localhost:8000/api/admin/characters/patient \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "'$PL_ID'",
    "session_id": "'$SESSION_ID'",
    "name": "林默",
    "soul_color": "C",
    "gender": "男",
    "age": 28,
    "identity": "前数据分析师",
    "personality_archives": {
      "C": "我总是在深夜思考，那些数据背后是否隐藏着什么",
      "M": "那天我在暴雨中狂奔，仿佛要甩掉所有枷锁",
      "Y": "和朋友们在天台看日落，那一刻什么都不用想",
      "K": "即使全世界都说不可能，我也要找到那个答案"
    },
    "ideal_projection": "我想成为一个能看穿一切谎言的存在"
  }'
# → 返回 patient_id 和 swap_file，将 SWAP 文件交给玩家B
# → 记录 patient_id 为 $PATIENT_ID

# 玩家B 根据 SWAP 文件创建幽灵
curl -s -X POST http://localhost:8000/api/admin/characters/ghost \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "'$PATIENT_ID'",
    "creator_player_id": "'$PL2_ID'",
    "session_id": "'$SESSION_ID'",
    "name": "Echo",
    "soul_color": "C",
    "appearance": "半透明的蓝色人形光影",
    "personality": "冷静而好奇",
    "print_abilities": [
      {
        "name": "数据逆流",
        "color": "C",
        "description": "创造一道逆流的数据瀑布，暂时扭曲因果逻辑",
        "ability_count": 2
      }
    ]
  }'
# → 记录 ghost_id 和 ability_id
```

### 4. 开始会话

```bash
curl -s -X POST http://localhost:8000/api/bot/events \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"player_id\": \"$KP_ID\",
    \"payload\": {\"event_type\": \"session_start\"}
  }"
```

### 5. 技能检定

```bash
curl -s -X POST http://localhost:8000/api/bot/events \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"player_id\": \"$PL_ID\",
    \"payload\": {
      \"event_type\": \"skill_check\",
      \"color\": \"C\",
      \"difficulty\": 3,
      \"context\": \"分析扇区数据流，寻找异常信号\"
    }
  }"
# → 返回投骰结果、成功/失败、叙述文本
```

### 6. 战斗

```bash
curl -s -X POST http://localhost:8000/api/bot/events \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"player_id\": \"$PL_ID\",
    \"payload\": {
      \"event_type\": \"attack\",
      \"attacker_ghost_id\": \"$GHOST_ID\",
      \"target_ghost_id\": \"$TARGET_GHOST_ID\",
      \"color_used\": \"C\"
    }
  }"
# → 返回命中/未中、伤害、HP 变动、碎片获取、坍缩检测
```

### 7. 查询时间线

```bash
curl -s http://localhost:8000/api/bot/sessions/$SESSION_ID/timeline
# → 所有事件的有序记录
```

### 8. 结束会话

```bash
curl -s -X POST http://localhost:8000/api/bot/events \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"player_id\": \"$KP_ID\",
    \"payload\": {\"event_type\": \"session_end\"}
  }"
```

---

## 测试

```bash
# 运行全部测试
uv run pytest

# 带详细输出
uv run pytest -v

# 仅运行骰子单元测试
uv run pytest tests/test_dice.py

# 仅运行 API 集成测试
uv run pytest tests/test_api.py

# 仅运行端到端场景测试
uv run pytest tests/test_e2e.py
```

测试使用内存 SQLite + MockProvider，无需外部依赖即可运行。

---

## 数据库迁移

开发模式下启动时会自动建表。生产环境使用 Alembic：

```bash
# 生成迁移脚本（根据模型变更）
uv run alembic revision --autogenerate -m "描述"

# 执行迁移
uv run alembic upgrade head

# 回退一步
uv run alembic downgrade -1

# 查看当前版本
uv run alembic current
```
