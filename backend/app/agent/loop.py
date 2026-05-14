"""Agent ReAct loop with native tool calling for OpenAI-compatible providers.

Flow:
1. Send the conversation (with tools attached) to the model.
2. Stream the assistant's text and any tool_call deltas.
3. When the model finishes, if there are tool calls: execute them, append their
   results as `tool` messages, and loop.
4. Stop when finish_reason='stop' (or 'length') and no pending tool calls, or
   when max_steps is exceeded.

Each iteration emits SSE-style events the API layer forwards to the client.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

from ..providers import ChatMessage, ChatRequest, ToolCall, ToolDef
from ..router import stream_chat
from ..tools import ToolContext, get_tool, tool_definitions


class AgentEventKind(str, Enum):
    STATUS = "status"
    THOUGHT_DELTA = "thought_delta"
    ASSISTANT_DELTA = "assistant_delta"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESOLVED = "approval_resolved"
    FINISHED = "finished"


@dataclass
class AgentEvent:
    kind: AgentEventKind
    payload: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> dict[str, Any]:
        return {"event": self.kind.value, "data": self.payload}


@dataclass
class AccumulatingToolCall:
    """A tool call assembled from multiple streaming deltas."""

    id: str = ""
    name: str = ""
    arguments_text: str = ""

    def to_call(self) -> ToolCall:
        try:
            args = json.loads(self.arguments_text) if self.arguments_text else {}
        except json.JSONDecodeError:
            args = {"_raw_arguments": self.arguments_text}
        return ToolCall(id=self.id or "call_unknown", name=self.name, arguments=args)


DEFAULT_AGENT_SYSTEM = """\
You are faux_code, an autonomous AI engineer running on the user's machine. You can:

- Read and search files in the workspace (tools: list_dir, read_file, grep)
- Edit files (tools: write_file, edit_file)
- Run shell commands (tool: shell) for git, build, test, etc.
- Run Python snippets (tool: python)
- Search the public web (tool: web_search) and fetch pages (tool: web_fetch)
- Search the local knowledge base (tool: rag_search)

Working style:
1. Think briefly, then act with tool calls. Prefer one tool call at a time.
2. Read before you write. Use `read_file` or `grep` before editing.
3. After making changes, validate with `shell` (run tests, type-check, lint).
4. When done, finish with a concise summary of what changed and why.
5. Never invent file paths — always confirm with `list_dir` first.
6. If a tool returns an error, read it and fix the approach instead of retrying blindly.
"""


class AgentLoop:
    def __init__(
        self,
        *,
        provider: Optional[str],
        model: str,
        goal: str,
        history: list[ChatMessage] | None = None,
        workspace: Optional[str] = None,
        approval_mode: str = "auto",
        allowed_tools: list[str] | None = None,
        max_steps: int = 25,
        system_prompt: Optional[str] = None,
        request_approval: Optional[Callable[[str, dict[str, Any]], Awaitable[bool]]] = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.goal = goal
        self.workspace = workspace
        self.approval_mode = approval_mode
        self.allowed_tools = allowed_tools
        self.max_steps = max_steps
        self.request_approval = request_approval

        from pathlib import Path as _P

        self.ctx = ToolContext(
            workspace=_P(workspace).resolve() if workspace else None,
            approval_mode=approval_mode,
            request_approval=request_approval,
        )

        system_messages: list[ChatMessage] = []
        if system_prompt:
            system_messages.append(ChatMessage(role="system", content=system_prompt))
        else:
            system_messages.append(ChatMessage(role="system", content=DEFAULT_AGENT_SYSTEM))

        self.messages: list[ChatMessage] = system_messages
        if history:
            self.messages.extend(history)
        self.messages.append(
            ChatMessage(role="user", content=goal)
        )

    @property
    def tools(self) -> list[ToolDef]:
        return tool_definitions(self.allowed_tools)

    async def run(self) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(AgentEventKind.STATUS, {"status": "running", "model": self.model})

        for step in range(self.max_steps):
            req = ChatRequest(
                model=self.model,
                messages=self.messages,
                tools=self.tools,
                temperature=0.3,
                top_p=0.9,
            )
            assistant_text = ""
            pending: dict[int, AccumulatingToolCall] = {}
            finish_reason: Optional[str] = None

            try:
                async for chunk in stream_chat(req, self.provider):
                    if chunk.delta:
                        assistant_text += chunk.delta
                        yield AgentEvent(
                            AgentEventKind.ASSISTANT_DELTA,
                            {"delta": chunk.delta, "step": step},
                        )
                    if chunk.tool_call_delta:
                        idx = int(chunk.tool_call_delta.get("index", 0) or 0)
                        accum = pending.setdefault(idx, AccumulatingToolCall())
                        if chunk.tool_call_delta.get("id"):
                            accum.id = chunk.tool_call_delta["id"]
                        fn = chunk.tool_call_delta.get("function", {}) or {}
                        if fn.get("name"):
                            accum.name = fn["name"]
                        if fn.get("arguments"):
                            accum.arguments_text += fn["arguments"]
                    if chunk.finish_reason:
                        finish_reason = chunk.finish_reason
            except Exception as e:
                yield AgentEvent(AgentEventKind.ERROR, {"message": str(e), "step": step})
                return

            # Emit the assistant message we just got.
            tool_calls = [ac.to_call() for ac in pending.values() if ac.name]
            assistant_msg = ChatMessage(
                role="assistant",
                content=assistant_text,
                tool_calls=tool_calls,
            )
            self.messages.append(assistant_msg)
            yield AgentEvent(
                AgentEventKind.ASSISTANT_MESSAGE,
                {
                    "content": assistant_text,
                    "tool_calls": [tc.model_dump() for tc in tool_calls],
                    "step": step,
                    "finish_reason": finish_reason,
                },
            )

            if not tool_calls:
                # Done — model produced a final reply with no tool calls.
                yield AgentEvent(
                    AgentEventKind.FINISHED,
                    {
                        "status": "completed",
                        "final": assistant_text,
                        "steps_taken": step + 1,
                    },
                )
                return

            # Execute each tool call sequentially.
            for tc in tool_calls:
                yield AgentEvent(
                    AgentEventKind.TOOL_CALL,
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "step": step,
                    },
                )
                try:
                    tool = get_tool(tc.name)
                except KeyError:
                    err = f"Unknown tool: {tc.name}"
                    self.messages.append(
                        ChatMessage(role="tool", content=err, tool_call_id=tc.id, name=tc.name)
                    )
                    yield AgentEvent(
                        AgentEventKind.TOOL_RESULT,
                        {"id": tc.id, "name": tc.name, "ok": False, "content": err},
                    )
                    continue
                try:
                    result = await tool.handler(tc.arguments, self.ctx)
                except Exception as e:
                    err = f"Tool '{tc.name}' raised: {e}"
                    self.messages.append(
                        ChatMessage(role="tool", content=err, tool_call_id=tc.id, name=tc.name)
                    )
                    yield AgentEvent(
                        AgentEventKind.TOOL_RESULT,
                        {"id": tc.id, "name": tc.name, "ok": False, "content": err},
                    )
                    continue
                payload = result.content
                if not payload:
                    payload = json.dumps(result.data) if result.data else "(no output)"
                self.messages.append(
                    ChatMessage(
                        role="tool",
                        content=payload,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )
                yield AgentEvent(
                    AgentEventKind.TOOL_RESULT,
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "ok": result.ok,
                        "is_error": result.is_error,
                        "content": result.content,
                        "data": result.data,
                    },
                )

        yield AgentEvent(
            AgentEventKind.FINISHED,
            {
                "status": "max_steps_exceeded",
                "steps_taken": self.max_steps,
            },
        )


async def run_agent(**kwargs) -> AsyncIterator[AgentEvent]:
    loop = AgentLoop(**kwargs)
    async for ev in loop.run():
        yield ev
