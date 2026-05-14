"""SQLModel schema for conversations, agent runs, API keys, and RAG documents."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Conversation(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    title: str = "New conversation"
    provider: str = "ollama"
    model: str = ""
    system_prompt: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    pinned: bool = False
    workspace_path: Optional[str] = None


class Message(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    conversation_id: str = Field(index=True)
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args_json: Optional[str] = None
    tool_result_json: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    created_at: datetime = Field(default_factory=_now)


class AgentRun(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    conversation_id: Optional[str] = Field(default=None, index=True)
    goal: str
    workspace_path: Optional[str] = None
    provider: str = "ollama"
    model: str = ""
    status: str = "pending"  # pending|running|awaiting_approval|completed|failed|cancelled
    approval_mode: str = "auto"  # auto|require_for_writes|require_all
    max_steps: int = 25
    steps_taken: int = 0
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class AgentEvent(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    run_id: str = Field(index=True)
    kind: str  # thought|tool_call|tool_result|message|error|approval_request|approval_decision|status
    payload_json: str
    created_at: datetime = Field(default_factory=_now)


class ApiKey(SQLModel, table=True):
    provider: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=_now)


class Document(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    collection: str = Field(index=True, default="default")
    title: str = ""
    source_path: str = ""
    mime_type: str = ""
    n_chunks: int = 0
    created_at: datetime = Field(default_factory=_now)


class DocumentChunk(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    document_id: str = Field(index=True)
    collection: str = Field(index=True, default="default")
    chunk_index: int = 0
    text: str
    created_at: datetime = Field(default_factory=_now)
