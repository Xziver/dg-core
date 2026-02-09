# dg-engine —— 世界引擎实现规范（Copilot 输入文档）

本文档定义 dg-engine 的 职责、结构、调用模型
Copilot 应严格遵循本规范生成代码。

## dg-engine 的核心定义

dg-engine = 世界引擎服务（World Engine Service）
它负责：
- 接收外部事件（来自 Bot / Web / Game）
- 维护世界状态（玩家、时间线、规则）
- 调用能力模块（LLM / RAG / Dice）
- 生成世界结果（文本 / 结构化事件）

dg-engine 不关心“客户端长什么样”

## dg-engine 的技术形态

类型：长期运行的后端服务
通信方式：HTTP API（Bot）+ gRPC（Web）
框架：FastAPI
数据源：
- DB（状态）
- RAG（知识）
- LLM（叙述）

## dg-engine 内部目录规范
```
dg-engine/
├─ app/
│  ├─ main.py                  # 启动入口（FastAPI）
│
│  ├─ api/                     # 对外 API
│  │   ├─ bot.py
│  │   ├─ web.py
│  │   └─ admin.py
│  │
│  ├─ domain/                  # 世界引擎核心
│  │   ├─ dispatcher.py        # 事件入口（唯一）
│  │   ├─ world.py             # 世界状态模型
│  │   ├─ character.py
│  │   ├─ session.py
│  │   ├─ rules/               # 世界规则
│  │   │   ├─ combat.py
│  │   │   ├─ skill.py
│  │   │   └─ narration.py
│  │   ├─ timeline.py          # 世界事件时间线
│  │   └─ context.py           # 当前会话 / 世界上下文
│  │
│  ├─ modules/                 # 能力模块
│  │   ├─ llm/
│  │   │   ├─ client.py        # LLM 抽象接口
│  │   │   └─ prompts.py       # Prompt 模板
│  │   ├─ rag/
│  │   │   ├─ retriever.py     # 检索接口
│  │   │   └─ index.py
│  │   ├─ dice/
│  │   │   └─ roller.py
│  │   └─ memory/
│  │       └─ short_term.py
│  │
│  ├─ infra/                   # 基础设施
│  │   ├─ db.py
│  │   ├─ cache.py
│  │   └─ config.py
│  │
│  └─ models/                  # 数据模型（DTO / Schema）
│      ├─ event.py
│      ├─ result.py
│      └─ world.py
│
├─ migrations/
├─ requirements.txt
└─ README.md
```

## 核心调用模型
### 事件流模型
```
Client
  ↓
Adapter
  ↓
API (FastAPI)
  ↓
domain.dispatcher
  ↓
domain.rules
  ↓
modules (llm / rag / dice)
  ↓
engine.timeline + world update
  ↓
Result
```

## engine 的本质
5.1 engine 不是 Autonomous Agent

- 不做“是否调用工具”的决策
- 不自由规划步骤

5.2 engine 是 世界状态机 + 规则系统

输入：结构化事件
输出：确定性结果 + 可选叙述

LLM 只用于：
- 风格化文本
- 世界叙述
- 设定问答（未来）

## LLM / RAG 接入原则
### LLM 使用规则

- 只能在 domain.rules 中调用
- 禁止在 api / adapter 中直接调用
- engine 不依赖具体 LLM 实现
```
from modules.llm.client import ask_llm
```

### RAG 使用规则

RAG = 世界知识
用于：
- 世界观查询
- 历史事件
- 设定补全
```
from modules.rag.retriever import query_knowledge
```

## code agent instruction
请严格按照本项目文档实现 dg-engine
不要引入多余抽象
以“世界引擎 + 可插拔能力模块”为核心目标