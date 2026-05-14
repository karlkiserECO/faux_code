"""Provider registry — singletons rebuilt on settings change."""

from __future__ import annotations

from .base import ProviderInfo
from .cerebras import CerebrasProvider
from .gemini import GeminiProvider
from .groq import GroqProvider
from .huggingface import HuggingFaceProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider
from .openrouter import OpenRouterProvider
from .vllm import VLLMProvider

_providers: dict[str, OpenAICompatProvider] | None = None


def _build() -> dict[str, OpenAICompatProvider]:
    return {
        "ollama": OllamaProvider(),
        "groq": GroqProvider(),
        "openrouter": OpenRouterProvider(),
        "gemini": GeminiProvider(),
        "cerebras": CerebrasProvider(),
        "huggingface": HuggingFaceProvider(),
        "vllm": VLLMProvider(),
    }


def _registry() -> dict[str, OpenAICompatProvider]:
    global _providers
    if _providers is None:
        _providers = _build()
    return _providers


def reload_providers() -> None:
    """Force-rebuild provider singletons (used after settings change)."""
    global _providers
    _providers = _build()


def get_provider(provider_id: str) -> OpenAICompatProvider:
    reg = _registry()
    if provider_id not in reg:
        raise KeyError(f"Unknown provider: {provider_id}")
    return reg[provider_id]


def list_providers() -> list[ProviderInfo]:
    return [p.info() for p in _registry().values()]


async def list_models() -> list[dict]:
    """Return merged model list across all enabled providers."""
    out: list[dict] = []
    for p in _registry().values():
        if not p.enabled:
            continue
        try:
            models = await p.list_models()
        except Exception:
            models = p.default_models
        for m in models:
            out.append({"id": m, "provider": p.id, "provider_name": p.name})
    return out
