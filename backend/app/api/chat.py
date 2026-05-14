"""Chat REST + SSE endpoints."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import Conversation, Message, get_session
from ..providers import ChatMessage, ChatRequest, ToolDef
from ..router import stream_chat
from ..streaming import event_stream

router = APIRouter(prefix="/v1", tags=["chat"])


class ChatCompletionRequest(BaseModel):
    conversation_id: Optional[str] = None
    provider: Optional[str] = None
    model: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float = 0.7
    top_p: float = 0.95
    max_tokens: Optional[int] = None
    fallback: list[str] = Field(default_factory=list)
    persist: bool = True
    system_prompt: Optional[str] = None


def _messages_from_payload(payload: list[dict[str, Any]]) -> list[ChatMessage]:
    out: list[ChatMessage] = []
    for m in payload:
        out.append(
            ChatMessage(
                role=m.get("role", "user"),
                content=m.get("content", "") or "",
                tool_call_id=m.get("tool_call_id"),
                name=m.get("name"),
            )
        )
    return out


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest, session: Session = Depends(get_session)
):
    messages = _messages_from_payload(body.messages)
    if body.system_prompt and not any(m.role == "system" for m in messages):
        messages.insert(0, ChatMessage(role="system", content=body.system_prompt))

    conversation: Conversation | None = None
    if body.persist:
        if body.conversation_id:
            conversation = session.get(Conversation, body.conversation_id)
        if conversation is None:
            conversation = Conversation(
                id=body.conversation_id or None,
                title=_derive_title(messages),
                provider=body.provider or "ollama",
                model=body.model,
                system_prompt=body.system_prompt or "",
            )
            if body.conversation_id:
                conversation.id = body.conversation_id
            session.add(conversation)
            session.commit()
            session.refresh(conversation)

        if messages and messages[-1].role == "user":
            session.add(
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content=messages[-1].content,
                )
            )
            session.commit()

    tools = [ToolDef(**t) for t in body.tools] if body.tools else []
    req = ChatRequest(
        model=body.model,
        messages=messages,
        tools=tools,
        temperature=body.temperature,
        top_p=body.top_p,
        max_tokens=body.max_tokens,
    )

    accumulated = []
    finish_reason: str | None = None
    usage: dict[str, int] | None = None

    async def gen():
        nonlocal finish_reason, usage
        if conversation:
            yield {"event": "conversation", "data": {"id": conversation.id, "title": conversation.title}}
        try:
            async for chunk in stream_chat(req, body.provider, body.fallback):
                if chunk.delta:
                    accumulated.append(chunk.delta)
                    yield {"event": "delta", "data": chunk.delta}
                if chunk.tool_call_delta:
                    yield {"event": "tool_call", "data": chunk.tool_call_delta}
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason
                if chunk.usage:
                    usage = chunk.usage
            if finish_reason:
                yield {"event": "finish", "data": {"reason": finish_reason, "usage": usage}}
        except Exception as exc:
            yield {"event": "error", "data": {"message": str(exc)}}
        finally:
            if conversation and body.persist and accumulated:
                text = "".join(accumulated)
                msg = Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=text,
                    provider=body.provider or "ollama",
                    model=body.model,
                    input_tokens=usage.get("input_tokens") if usage else None,
                    output_tokens=usage.get("output_tokens") if usage else None,
                )
                session.add(msg)
                from datetime import datetime, timezone

                conversation.updated_at = datetime.now(timezone.utc)
                session.add(conversation)
                session.commit()

    return StreamingResponse(event_stream(gen()), media_type="text/event-stream")


@router.get("/conversations")
def list_conversations(session: Session = Depends(get_session)):
    rows = session.exec(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(200)
    ).all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "provider": c.provider,
            "model": c.model,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "pinned": c.pinned,
        }
        for c in rows
    ]


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str, session: Session = Depends(get_session)):
    conv = session.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "Not found")
    msgs = session.exec(
        select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)
    ).all()
    return {
        "id": conv.id,
        "title": conv.title,
        "provider": conv.provider,
        "model": conv.model,
        "system_prompt": conv.system_prompt,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
                "provider": m.provider,
                "model": m.model,
                "tool_name": m.tool_name,
                "tool_args": json.loads(m.tool_args_json) if m.tool_args_json else None,
                "tool_result": json.loads(m.tool_result_json) if m.tool_result_json else None,
            }
            for m in msgs
        ],
    }


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: str, session: Session = Depends(get_session)):
    conv = session.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "Not found")
    for m in session.exec(select(Message).where(Message.conversation_id == conv_id)).all():
        session.delete(m)
    session.delete(conv)
    session.commit()
    return {"ok": True}


class RenameRequest(BaseModel):
    title: str


@router.patch("/conversations/{conv_id}")
def rename_conversation(
    conv_id: str, body: RenameRequest, session: Session = Depends(get_session)
):
    conv = session.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "Not found")
    conv.title = body.title
    session.add(conv)
    session.commit()
    return {"ok": True}


def _derive_title(messages: list[ChatMessage]) -> str:
    for m in messages:
        if m.role == "user" and m.content:
            t = m.content.strip().splitlines()[0]
            return t[:60] + ("…" if len(t) > 60 else "")
    return "New conversation"
