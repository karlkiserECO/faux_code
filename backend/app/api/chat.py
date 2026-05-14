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
    enable_tools: bool = False
    allowed_tools: Optional[list[str]] = None
    workspace: Optional[str] = None
    max_steps: int = 12
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

    if body.enable_tools:
        return StreamingResponse(
            event_stream(
                _agentic_chat_stream(
                    body=body,
                    conversation=conversation,
                    messages=messages,
                )
            ),
            media_type="text/event-stream",
        )

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


async def _agentic_chat_stream(
    *,
    body: ChatCompletionRequest,
    conversation: Optional[Conversation],
    messages: list[ChatMessage],
):
    """Drive the agent loop inside a chat conversation and forward unified events."""
    from ..agent import AgentEventKind, AgentLoop
    from ..db.session import _get_engine
    from sqlmodel import Session as _S
    from datetime import datetime, timezone

    if conversation:
        yield {"event": "conversation", "data": {"id": conversation.id, "title": conversation.title}}

    history = [m for m in messages if m.role != "user"][:]
    user_messages = [m for m in messages if m.role == "user"]
    goal = user_messages[-1].content if user_messages else ""
    prior = history + user_messages[:-1]
    system_prompt = body.system_prompt or None

    loop = AgentLoop(
        provider=body.provider,
        model=body.model,
        goal=goal,
        history=prior,
        workspace=body.workspace,
        approval_mode="auto",
        allowed_tools=body.allowed_tools,
        max_steps=body.max_steps,
        system_prompt=system_prompt,
    )

    final_text = ""
    tool_events: list[dict[str, Any]] = []
    buffered_step: int | None = None
    buffered_text = ""
    streamed_chars = 0  # how many chars of buffered_text we've already emitted as deltas

    def looks_like_tool_json(s: str) -> bool:
        """Heuristic: very early in a turn the model is starting JSON-style tool call."""
        t = s.lstrip()
        if not t:
            return False
        if t.startswith("```"):
            # Could be ```json or a code block — wait until we see more.
            head = t[: min(80, len(t))].lower()
            if "json" in head or "tool" in head or "function" in head:
                return True
            # Plain code fence — treat as prose so user sees code.
            return False
        if t.startswith("<tool_call>"):
            return True
        if t.startswith("{") or t.startswith("["):
            head = t[: min(120, len(t))]
            return '"name"' in head or '"tool"' in head or '"function"' in head
        return False

    try:
        async for ev in loop.run():
            if ev.kind == AgentEventKind.ASSISTANT_DELTA:
                step = ev.payload.get("step", 0)
                if buffered_step != step:
                    buffered_step = step
                    buffered_text = ""
                    streamed_chars = 0
                buffered_text += ev.payload.get("delta", "")
                # Once we've decided it's NOT a tool call, stream the tail through.
                if streamed_chars and len(buffered_text) > streamed_chars:
                    new_chunk = buffered_text[streamed_chars:]
                    streamed_chars = len(buffered_text)
                    yield {"event": "delta", "data": new_chunk}
                elif not streamed_chars and len(buffered_text) >= 12:
                    # Enough characters to decide.
                    if not looks_like_tool_json(buffered_text):
                        yield {"event": "delta", "data": buffered_text}
                        streamed_chars = len(buffered_text)
            elif ev.kind == AgentEventKind.ASSISTANT_MESSAGE:
                content = ev.payload.get("content", "")
                # If we haven't streamed anything but content is real, emit it.
                if content and streamed_chars == 0:
                    yield {"event": "delta", "data": content}
                if content:
                    final_text = content
                buffered_step = None
                buffered_text = ""
                streamed_chars = 0
            elif ev.kind == AgentEventKind.TOOL_CALL:
                tool_events.append(
                    {
                        "id": ev.payload.get("id"),
                        "name": ev.payload.get("name"),
                        "arguments": ev.payload.get("arguments"),
                        "step": ev.payload.get("step", 0),
                        "result": None,
                    }
                )
                yield {"event": "tool_call_started", "data": ev.payload}
            elif ev.kind == AgentEventKind.TOOL_RESULT:
                for te in tool_events:
                    if te["id"] == ev.payload.get("id") and te["result"] is None:
                        te["result"] = {
                            "ok": ev.payload.get("ok"),
                            "is_error": ev.payload.get("is_error"),
                            "content": ev.payload.get("content"),
                        }
                yield {"event": "tool_result", "data": ev.payload}
            elif ev.kind == AgentEventKind.FINISHED:
                if ev.payload.get("final"):
                    final_text = ev.payload["final"]
                yield {
                    "event": "finish",
                    "data": {
                        "reason": ev.payload.get("status", "completed"),
                        "usage": None,
                        "steps_taken": ev.payload.get("steps_taken"),
                    },
                }
            elif ev.kind == AgentEventKind.ERROR:
                yield {"event": "error", "data": {"message": ev.payload.get("message", "agent error")}}
    except Exception as exc:
        yield {"event": "error", "data": {"message": str(exc)}}

    # Persist the final assistant message + tool messages.
    if conversation and body.persist and (final_text or tool_events):
        with _S(_get_engine()) as s:
            for te in tool_events:
                s.add(
                    Message(
                        conversation_id=conversation.id,
                        role="tool",
                        content=(te.get("result") or {}).get("content", "") or "",
                        tool_call_id=te.get("id"),
                        tool_name=te.get("name"),
                        tool_args_json=json.dumps(te.get("arguments")) if te.get("arguments") is not None else None,
                        tool_result_json=json.dumps(te.get("result")) if te.get("result") else None,
                    )
                )
            if final_text:
                s.add(
                    Message(
                        conversation_id=conversation.id,
                        role="assistant",
                        content=final_text,
                        provider=body.provider or "ollama",
                        model=body.model,
                    )
                )
            conv = s.get(Conversation, conversation.id)
            if conv:
                conv.updated_at = datetime.now(timezone.utc)
                s.add(conv)
            s.commit()


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


class PinRequest(BaseModel):
    pinned: bool


@router.patch("/conversations/{conv_id}/pin")
def pin_conversation(
    conv_id: str, body: PinRequest, session: Session = Depends(get_session)
):
    conv = session.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "Not found")
    conv.pinned = body.pinned
    session.add(conv)
    session.commit()
    return {"ok": True}


@router.delete("/conversations/{conv_id}/messages/{msg_id}")
def delete_message_and_after(
    conv_id: str, msg_id: str, session: Session = Depends(get_session)
):
    """Delete a message and every message after it. Used by 'regenerate' and 'edit'."""
    target = session.get(Message, msg_id)
    if not target or target.conversation_id != conv_id:
        raise HTTPException(404, "Not found")
    later = session.exec(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .where(Message.created_at >= target.created_at)
    ).all()
    for m in later:
        session.delete(m)
    session.commit()
    return {"ok": True, "deleted": len(later)}


class TitleRequest(BaseModel):
    provider: Optional[str] = None
    model: str


@router.post("/conversations/{conv_id}/title")
async def generate_title(
    conv_id: str, body: TitleRequest, session: Session = Depends(get_session)
):
    """Generate a 3-7 word title from the first user message + assistant reply."""
    conv = session.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "Not found")
    msgs = session.exec(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at)
    ).all()
    if not msgs:
        return {"title": conv.title}

    transcript_bits: list[str] = []
    for m in msgs[:4]:
        text = (m.content or "").strip()
        if not text:
            continue
        transcript_bits.append(f"{m.role.upper()}: {text[:500]}")
    transcript = "\n".join(transcript_bits)

    prompt = (
        "Write a 3-7 word title that summarizes the conversation below. "
        "Respond with ONLY the title, no quotes, no punctuation at the end.\n\n"
        f"{transcript}"
    )

    title_messages = [ChatMessage(role="user", content=prompt)]
    req = ChatRequest(
        model=body.model,
        messages=title_messages,
        temperature=0.2,
        max_tokens=24,
    )
    text = ""
    try:
        from ..router import stream_chat as _stream

        async for chunk in _stream(req, body.provider):
            if chunk.delta:
                text += chunk.delta
            if chunk.finish_reason:
                break
    except Exception:
        text = ""
    title = text.strip().splitlines()[0] if text.strip() else ""
    # Strip common LLM preambles like "Title: " or "Here's a title: ".
    for prefix in ("title:", "title is:", "the title is:", "here is the title:", "here's the title:"):
        if title.lower().startswith(prefix):
            title = title[len(prefix):].strip()
    title = title.strip(' "\'\u201c\u201d`*:-.')
    if not title:
        title = _derive_title(
            [ChatMessage(role=m.role, content=m.content or "") for m in msgs]
        )
    title = title[:80]
    conv.title = title
    session.add(conv)
    session.commit()
    return {"title": title}


def _derive_title(messages: list[ChatMessage]) -> str:
    for m in messages:
        if m.role == "user" and m.content:
            t = m.content.strip().splitlines()[0]
            return t[:60] + ("…" if len(t) > 60 else "")
    return "New conversation"
