# 01 — LLM 实现规范

> 本文档定义 dg-engine 中 LLM 模块的职责、接口设计与调用约束。
> Copilot / Code Agent 应严格遵循本规范生成代码。

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 多模型兼容 | 同时支持 OpenAI-compatible API 和 Anthropic Claude，通过配置切换 |
| 职责单一 | LLM 仅用于**文本风格化**与**世界叙述生成**，不参与游戏逻辑判定 |
| 可 Mock | MVP 阶段可使用 MockProvider 返回模板文本，不依赖真实 LLM 服务 |
| 调用可控 | 所有 LLM 调用必须经过 `modules.llm.client`，且只能由 `domain.rules` 发起 |

---

## 2. 多模型抽象接口（Provider Pattern）

### 2.1 接口定义

```python
# app/modules/llm/client.py

from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


class LLMRequest(BaseModel):
    """LLM 调用请求体"""
    prompt: str
    system_message: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1024


class LLMResponse(BaseModel):
    """LLM 调用响应体"""
    content: str
    model: str
    usage: dict  # {"prompt_tokens": int, "completion_tokens": int}


class LLMProvider(ABC):
    """LLM 供应商抽象基类"""

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """发送请求并返回生成结果"""
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """返回供应商标识，用于日志和调试"""
        ...
```

### 2.2 Provider 实现

```
app/modules/llm/
├── client.py              # LLMProvider 抽象 + ask_llm() 入口
├── providers/
│   ├── __init__.py
│   ├── openai_compat.py   # OpenAI-compatible API Provider
│   ├── anthropic.py       # Anthropic Claude Provider
│   └── mock.py            # MockProvider（返回模板文本）
└── prompts.py             # Prompt 模板管理
```

#### OpenAI-compatible Provider

```python
# app/modules/llm/providers/openai_compat.py

import httpx
from app.modules.llm.client import LLMProvider, LLMRequest, LLMResponse


class OpenAICompatProvider(LLMProvider):
    """兼容所有 OpenAI API 格式的供应商（OpenAI / DeepSeek / vLLM 等）"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        messages = []
        if request.system_message:
            messages.append({"role": "system", "content": request.system_message})
        messages.append({"role": "user", "content": request.prompt})

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"]["content"],
            model=data["model"],
            usage=data.get("usage", {}),
        )

    def provider_name(self) -> str:
        return f"openai_compat({self.model})"
```

#### Anthropic Claude Provider

```python
# app/modules/llm/providers/anthropic.py

import httpx
from app.modules.llm.client import LLMProvider, LLMRequest, LLMResponse


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API Provider"""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system_message:
            body["system"] = request.system_message

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.API_URL, headers=headers, json=body, timeout=60.0
            )
            resp.raise_for_status()
            data = resp.json()

        return LLMResponse(
            content=data["content"][0]["text"],
            model=data["model"],
            usage={
                "prompt_tokens": data["usage"]["input_tokens"],
                "completion_tokens": data["usage"]["output_tokens"],
            },
        )

    def provider_name(self) -> str:
        return f"anthropic({self.model})"
```

#### Mock Provider

```python
# app/modules/llm/providers/mock.py

from app.modules.llm.client import LLMProvider, LLMRequest, LLMResponse


class MockProvider(LLMProvider):
    """Mock Provider，用于 MVP 阶段测试，返回固定模板文本"""

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=f"[MOCK] 基于以下 prompt 的模拟输出:\n{request.prompt[:100]}...",
            model="mock-v1",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
        )

    def provider_name(self) -> str:
        return "mock"
```

### 2.3 Provider 工厂与统一入口

```python
# app/modules/llm/client.py（补充）

from app.infra.config import settings

_provider: Optional[LLMProvider] = None


def get_provider() -> LLMProvider:
    """根据配置返回对应的 LLM Provider 单例"""
    global _provider
    if _provider is not None:
        return _provider

    if settings.LLM_PROVIDER == "openai_compat":
        from app.modules.llm.providers.openai_compat import OpenAICompatProvider
        _provider = OpenAICompatProvider(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
        )
    elif settings.LLM_PROVIDER == "anthropic":
        from app.modules.llm.providers.anthropic import AnthropicProvider
        _provider = AnthropicProvider(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
        )
    elif settings.LLM_PROVIDER == "mock":
        from app.modules.llm.providers.mock import MockProvider
        _provider = MockProvider()
    else:
        raise ValueError(f"未知的 LLM_PROVIDER: {settings.LLM_PROVIDER}")

    return _provider


async def ask_llm(prompt: str, system_message: Optional[str] = None, **kwargs) -> str:
    """统一 LLM 调用入口 —— domain.rules 唯一应调用的函数"""
    provider = get_provider()
    request = LLMRequest(prompt=prompt, system_message=system_message, **kwargs)
    response = await provider.generate(request)
    return response.content
```

### 2.4 配置项

```env
# .env

LLM_PROVIDER=mock            # mock | openai_compat | anthropic
LLM_BASE_URL=https://api.openai.com   # OpenAI-compatible 专用
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4o-mini
```

```python
# app/infra/config.py（LLM 相关字段）

class Settings(BaseSettings):
    LLM_PROVIDER: str = "mock"
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
```

---

## 3. LLM 调用场景

LLM 在引擎中**不参与逻辑判定**，仅用于以下三类场景：

### 3.1 叙述风格化（Narrative Stylization）

| 项目 | 说明 |
|------|------|
| 触发时机 | 战斗结算后、技能检定后、场景切换时 |
| 输入 | 结构化事件结果（如 `{attacker, target, damage, success}`) |
| 输出 | 风格化叙述文本 |
| 示例场景 | 战斗叙述、技能检定结果描述 |

### 3.2 世界描述生成（World Description）

| 项目 | 说明 |
|------|------|
| 触发时机 | 进入新场景、新扇区开启 |
| 输入 | 场景元数据 + RAG 检索到的世界设定 |
| 输出 | 沉浸式场景描述文本 |
| 示例场景 | 扇区入口描述、环境变化描述 |

### 3.3 设定问答（Lore Q&A）

| 项目 | 说明 |
|------|------|
| 触发时机 | 管理员 / DM 查询世界设定 |
| 输入 | 用户问题 + RAG 检索结果 |
| 输出 | 基于知识库的问答回复 |
| 示例场景 | "灰山城的四个扇区分别有什么特点？" |

---

## 4. Prompt 模板管理

### 4.1 模板分类

所有 Prompt 模板集中存放在 `app/modules/llm/prompts.py`，按场景分类：

```python
# app/modules/llm/prompts.py

from string import Template


# ========== 系统人格 ==========
SYSTEM_NARRATOR = """你是灰山城的叙述者——系统管理员AI小倩。
你的语言风格：略带忧郁的温柔、偶尔流露出不经意的幽默、
对患者们有真诚的关切但不会过度煽情。
你使用中文叙述，必要时嵌入技术术语（如"量子活性""数据碎片"等）。
输出纯叙述文本，不要包含 JSON 或 markdown 格式。"""


# ========== 战斗叙述 ==========
COMBAT_NARRATION = Template("""请为以下战斗结果生成一段叙述（100-200字）：

攻击者：$attacker_name（底色：$attacker_color）
目标：$target_name
使用能力：$ability_name
骰子结果：$dice_result
伤害：$damage
是否成功：$success

场景背景：$scene_context""")


# ========== 场景描述 ==========
SCENE_DESCRIPTION = Template("""请为以下场景生成沉浸式描述（150-300字）：

扇区名称：$sector_name
区域名称：$area_name
环境特征：$environment
当前状态：$world_state

已知世界设定（参考资料）：
$rag_context""")


# ========== NPC 对话 ==========
NPC_DIALOGUE = Template("""请以以下 NPC 的身份进行对话回复（50-150字）：

NPC名称：$npc_name
NPC性格：$npc_personality
NPC当前状态：$npc_state

玩家发言：$player_message

对话历史：
$dialogue_history""")


# ========== 技能检定结果 ==========
SKILL_CHECK_RESULT = Template("""请为以下技能检定结果生成叙述（80-150字）：

执行者：$actor_name
检定类型：$check_type（对应颜色：$color）
骰子数量：$dice_count
骰子结果：$dice_values
成功阈值：$threshold
是否成功：$success

行动描述：$action_description""")


# ========== 设定问答 ==========
LORE_QA = Template("""基于以下世界设定资料，回答用户的问题。
如果资料中未提及，请明确说明"当前资料中未找到相关信息"。

参考资料：
$rag_context

用户问题：$question""")
```

### 4.2 模板使用方式

```python
# 在 domain/rules/narration.py 中使用

from app.modules.llm.client import ask_llm
from app.modules.llm.prompts import SYSTEM_NARRATOR, COMBAT_NARRATION


async def narrate_combat(result: CombatResult, scene_ctx: str) -> str:
    prompt = COMBAT_NARRATION.substitute(
        attacker_name=result.attacker.name,
        attacker_color=result.attacker.base_color,
        target_name=result.target.name,
        ability_name=result.ability_used or "普通攻击",
        dice_result=str(result.dice_values),
        damage=result.damage,
        success="成功" if result.success else "失败",
        scene_context=scene_ctx,
    )
    return await ask_llm(prompt=prompt, system_message=SYSTEM_NARRATOR)
```

### 4.3 模板扩展规范

| 规则 | 说明 |
|------|------|
| 命名 | 全大写 + 下划线，如 `COMBAT_NARRATION` |
| 类型 | 使用 `string.Template`，变量以 `$var` 标记 |
| 长度控制 | 在模板中明确指定期望输出字数范围 |
| 新增模板 | 追加到 `prompts.py` 对应分类区域，不新建文件 |

---

## 5. 调用约束

### 5.1 调用链路（强制）

```
domain.rules.*
    └── modules.llm.client.ask_llm()
            └── LLMProvider.generate()
```

### 5.2 禁止事项

| 禁止行为 | 原因 |
|----------|------|
| 在 `api/` 层直接调用 `ask_llm` | 违反分层架构，API 层不应有业务逻辑 |
| 在 `domain.dispatcher` 中调用 `ask_llm` | dispatcher 只做事件路由，不处理具体逻辑 |
| 在 LLM 返回结果中解析 JSON 作为游戏判定 | 引擎是确定性状态机，不依赖 LLM 做逻辑判定 |
| 让 LLM 决定骰子结果或伤害数值 | 数值计算由 `modules.dice` 和 `domain.rules` 处理 |

### 5.3 错误处理

```python
# LLM 调用失败时的降级策略

async def ask_llm_safe(prompt: str, fallback: str = "", **kwargs) -> str:
    """带降级的 LLM 调用 —— 失败时返回 fallback 文本"""
    try:
        return await ask_llm(prompt=prompt, **kwargs)
    except Exception as e:
        logger.warning(f"LLM 调用失败，使用降级文本: {e}")
        return fallback or "[系统叙述暂时不可用]"
```

### 5.4 调用频率建议

| 场景 | 频率 | 说明 |
|------|------|------|
| 战斗叙述 | 每回合 1 次 | 仅在结算完成后调用 |
| 场景描述 | 场景切换时 1 次 | 可缓存至场景结束 |
| NPC 对话 | 每次对话 1 次 | 单轮对话单次调用 |
| 技能检定叙述 | 每次检定 1 次 | 检定结果确定后调用 |
| 设定问答 | 按需 | 管理员 / DM 手动触发 |

---

## 6. 测试策略

### 6.1 单元测试

- 所有测试默认使用 `MockProvider`
- 验证 Prompt 模板变量替换正确性
- 验证 `ask_llm` 在 Provider 异常时的降级行为

### 6.2 集成测试（可选）

- 配置真实 Provider 后验证端到端调用
- 验证返回文本非空且在合理长度范围内
- 集成测试通过环境变量 `LLM_INTEGRATION_TEST=1` 开关控制

```python
# tests/modules/llm/test_client.py

import pytest
from app.modules.llm.client import ask_llm, get_provider
from app.modules.llm.providers.mock import MockProvider


@pytest.fixture(autouse=True)
def use_mock_provider(monkeypatch):
    """测试环境强制使用 MockProvider"""
    monkeypatch.setattr("app.modules.llm.client._provider", MockProvider())


@pytest.mark.asyncio
async def test_ask_llm_returns_string():
    result = await ask_llm(prompt="测试 prompt")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_ask_llm_with_system_message():
    result = await ask_llm(
        prompt="描述一个场景",
        system_message="你是叙述者"
    )
    assert isinstance(result, str)
```
