"""Provider router with fallback chain.

Given a (provider, model) preference, route the request, and on failure fall back
to a configured chain of alternatives.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from .providers import ChatChunk, ChatRequest, get_provider, list_providers
from .providers.openai_compat import OpenAICompatProvider


class RouterError(RuntimeError):
    pass


def resolve_provider(provider_id: str | None, model: str | None) -> OpenAICompatProvider:
    """Resolve a provider, defaulting to Ollama when not specified."""
    if provider_id:
        return get_provider(provider_id)
    # No provider given — pick the first enabled one (preferring local).
    enabled = [p for p in list_providers() if p.enabled]
    if not enabled:
        return get_provider("ollama")
    for prio in ("ollama", "groq", "gemini", "openrouter", "cerebras", "huggingface", "vllm"):
        for p in enabled:
            if p.id == prio:
                return get_provider(prio)
    return get_provider(enabled[0].id)


async def stream_chat(
    req: ChatRequest,
    provider_id: str | None = None,
    fallback_chain: list[str] | None = None,
) -> AsyncIterator[ChatChunk]:
    """Stream a chat completion with optional fallback chain."""
    primary = resolve_provider(provider_id, req.model)
    chain: list[OpenAICompatProvider] = [primary]
    for fb in fallback_chain or []:
        try:
            chain.append(get_provider(fb))
        except KeyError:
            continue

    last_err: Exception | None = None
    for p in chain:
        try:
            async for chunk in p.stream_chat(req):
                yield chunk
            return
        except Exception as exc:
            last_err = exc
            continue
    raise RouterError(f"All providers failed. Last error: {last_err}")
