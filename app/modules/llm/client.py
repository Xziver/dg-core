"""LLM provider abstraction — supports OpenAI-compatible, Anthropic, and Mock."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.infra.config import settings


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system: str | None = None, **kwargs: object) -> str:
        ...


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible API provider (works with any OpenAI-compatible endpoint)."""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, prompt: str, system: str | None = None, **kwargs: object) -> str:
        import httpx

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, **kwargs},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929") -> None:
        self.api_key = api_key
        self.model = model

    async def generate(self, prompt: str, system: str | None = None, **kwargs: object) -> str:
        import httpx

        body: dict = {
            "model": self.model,
            "max_tokens": kwargs.pop("max_tokens", 1024),  # type: ignore[arg-type]
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]


class MockProvider(LLMProvider):
    """Returns canned responses for testing."""

    async def generate(self, prompt: str, system: str | None = None, **kwargs: object) -> str:
        return f"[MockLLM] 收到 prompt（{len(prompt)} 字符）。这是一段模拟叙述文本。"


def get_llm_provider(config: object | None = None) -> LLMProvider:
    """Factory: return the configured LLM provider."""
    provider_name = settings.llm_provider.lower()
    if provider_name == "openai":
        return OpenAIProvider(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    elif provider_name == "anthropic":
        return AnthropicProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
    else:
        return MockProvider()


# Module-level singleton, initialized lazily
_provider: LLMProvider | None = None


def _get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = get_llm_provider()
    return _provider


async def ask_llm(prompt: str, system: str | None = None, **kwargs: object) -> str:
    """Unified entry point for LLM calls. Use this in domain.rules."""
    return await _get_provider().generate(prompt, system, **kwargs)


async def ask_llm_safe(
    prompt: str, system: str | None = None, fallback: str = "", **kwargs: object
) -> str:
    """Same as ask_llm but returns fallback on failure."""
    try:
        return await ask_llm(prompt, system, **kwargs)
    except Exception:
        return fallback
