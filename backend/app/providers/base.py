"""Base types and protocol for chat providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal, Optional, Protocol

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class ToolDef(BaseModel):
    """OpenAI-style tool definition."""

    type: Literal["function"] = "function"
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    tools: list[ToolDef] = Field(default_factory=list)
    temperature: float = 0.7
    top_p: float = 0.95
    max_tokens: Optional[int] = None
    stream: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)


class ChatChunk(BaseModel):
    """Unified streaming chunk.

    Exactly one of `delta`, `tool_call_delta`, `usage`, or `finish_reason` is set
    per chunk.
    """

    delta: str = ""
    tool_call_delta: Optional[dict[str, Any]] = None
    finish_reason: Optional[str] = None
    usage: Optional[dict[str, int]] = None
    raw: Optional[dict[str, Any]] = None


class ProviderInfo(BaseModel):
    id: str
    name: str
    enabled: bool
    requires_key: bool
    models: list[str] = Field(default_factory=list)
    description: str = ""


class BaseProvider(Protocol):
    id: str
    name: str

    async def list_models(self) -> list[str]: ...

    async def stream_chat(self, req: ChatRequest) -> AsyncIterator[ChatChunk]: ...

    def info(self) -> ProviderInfo: ...
