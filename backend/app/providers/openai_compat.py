"""Shared OpenAI-compatible streaming chat adapter.

Used by Groq, OpenRouter, Cerebras, Ollama, and self-hosted vLLM. They all
implement the OpenAI `/v1/chat/completions` SSE protocol with minor differences.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .base import ChatChunk, ChatMessage, ChatRequest, ProviderInfo, ToolDef


def _messages_to_openai(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        d: dict[str, Any] = {"role": m.role, "content": m.content or ""}
        if m.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in m.tool_calls
            ]
        if m.tool_call_id:
            d["tool_call_id"] = m.tool_call_id
        if m.name:
            d["name"] = m.name
        out.append(d)
    return out


def _tools_to_openai(tools: list[ToolDef]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


class OpenAICompatProvider:
    """Generic OpenAI-compatible provider."""

    def __init__(
        self,
        *,
        provider_id: str,
        name: str,
        base_url: str,
        api_key: str = "",
        requires_key: bool = True,
        default_models: list[str] | None = None,
        description: str = "",
        extra_headers: dict[str, str] | None = None,
        models_path: str = "/models",
        chat_path: str = "/chat/completions",
    ):
        self.id = provider_id
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.requires_key = requires_key
        self.default_models = default_models or []
        self.description = description
        self.extra_headers = extra_headers or {}
        self.models_path = models_path
        self.chat_path = chat_path

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        h.update(self.extra_headers)
        return h

    @property
    def enabled(self) -> bool:
        if not self.base_url:
            return False
        if self.requires_key and not self.api_key:
            return False
        return True

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            name=self.name,
            enabled=self.enabled,
            requires_key=self.requires_key,
            models=self.default_models,
            description=self.description,
        )

    async def list_models(self) -> list[str]:
        if not self.enabled:
            return self.default_models
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{self.base_url}{self.models_path}", headers=self._headers()
                )
                r.raise_for_status()
                data = r.json()
                models: list[str] = []
                for m in data.get("data", []) or []:
                    mid = m.get("id") or m.get("name")
                    if mid:
                        models.append(mid)
                if not models and isinstance(data.get("models"), list):
                    for m in data["models"]:
                        if isinstance(m, dict):
                            mid = m.get("id") or m.get("name")
                        else:
                            mid = m
                        if mid:
                            models.append(mid)
                return models or self.default_models
        except Exception:
            return self.default_models

    async def stream_chat(self, req: ChatRequest) -> AsyncIterator[ChatChunk]:
        if not self.enabled:
            raise RuntimeError(
                f"Provider '{self.id}' is not enabled (missing API key or base URL)."
            )
        payload: dict[str, Any] = {
            "model": req.model,
            "messages": _messages_to_openai(req.messages),
            "stream": True,
            "temperature": req.temperature,
            "top_p": req.top_p,
        }
        if req.max_tokens:
            payload["max_tokens"] = req.max_tokens
        if req.tools:
            payload["tools"] = _tools_to_openai(req.tools)
            payload["tool_choice"] = "auto"
        # Defensive stop sequences: only true end-of-turn tokens. We don't add
        # <|im_start|> here because some Qwen variants emit it as a separator
        # between multiple tool calls inside one completion; stopping there
        # would silently drop the model's follow-up call.
        default_stops = ["<|im_end|>", "<|endoftext|>"]
        existing_stops = req.extra.get("stop") if req.extra else None
        if isinstance(existing_stops, list):
            payload["stop"] = list({*existing_stops, *default_stops})
        elif isinstance(existing_stops, str):
            payload["stop"] = list({existing_stops, *default_stops})
        else:
            payload["stop"] = default_stops
        for k, v in (req.extra or {}).items():
            if k == "stop":
                continue
            payload[k] = v

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}{self.chat_path}",
                headers=self._headers(),
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"{self.id} HTTP {resp.status_code}: {body.decode('utf-8', 'ignore')[:500]}"
                    )
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                    else:
                        data = line.strip()
                    if data == "[DONE]":
                        return
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    async for chunk in self._parse_openai_chunk(obj):
                        yield chunk

    async def _parse_openai_chunk(self, obj: dict[str, Any]) -> AsyncIterator[ChatChunk]:
        choices = obj.get("choices") or []
        if not choices:
            usage = obj.get("usage")
            if usage:
                yield ChatChunk(
                    usage={
                        "input_tokens": usage.get("prompt_tokens", 0),
                        "output_tokens": usage.get("completion_tokens", 0),
                    },
                    raw=obj,
                )
            return
        choice = choices[0]
        delta = choice.get("delta") or choice.get("message") or {}
        if delta.get("content"):
            yield ChatChunk(delta=delta["content"], raw=obj)
        for tc in delta.get("tool_calls", []) or []:
            yield ChatChunk(tool_call_delta=tc, raw=obj)
        if choice.get("finish_reason"):
            usage = obj.get("usage") or {}
            yield ChatChunk(
                finish_reason=choice["finish_reason"],
                usage={
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                }
                if usage
                else None,
                raw=obj,
            )
