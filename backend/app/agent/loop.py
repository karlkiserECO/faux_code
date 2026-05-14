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
- Edit files (tools: write_file, edit_file, apply_patch)
- Run shell commands (tool: shell) for git, build, test, etc.
- Run Python snippets (tool: python) -- this always works, no PATH worries
- Inspect git state (tools: git_status, git_diff, git_log)
- Search the public web (tool: web_search) and fetch pages (tool: web_fetch)
- Search the local knowledge base (tool: rag_search)

Working style:
1. Think briefly, then act with tool calls. Prefer one tool call at a time.
2. Read before you write. Use `read_file` or `grep` before editing.
3. After making changes, validate with `shell` (run tests, type-check, lint).
4. When done, finish with a concise summary of what changed and why.
5. Never invent file paths -- always confirm with `list_dir` first.
6. If a tool returns an error, read it and fix the approach instead of retrying blindly.

Environment notes:
- macOS may not have `python` on PATH; prefer the `python` tool, or call `python3` in shell.
- Use the `apply_patch` tool when changes span multiple files.
- Multi-step refactors: read all affected files first, then edit each, then verify with shell.
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

        empty_streak = 0
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

            # Fallback: some models (notably some Qwen variants on Ollama)
            # emit tool calls as JSON in the text content instead of the
            # `tool_calls` field. Detect and recover.
            if not tool_calls and assistant_text:
                extra = _extract_json_tool_calls(assistant_text)
                if extra:
                    tool_calls = extra
                    assistant_text = ""  # don't double-render the JSON

            # Scrub leaked template tokens from text we'd show the user.
            if assistant_text:
                import re as _re

                assistant_text = _re.sub(
                    r"<\|(im_start|im_end|endoftext)\|>(?:assistant|user|system)?",
                    "",
                    assistant_text,
                ).strip()

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
                looks_like_plan = _looks_like_plan(assistant_text)
                halluc = _looks_like_hallucinated_tool_output(assistant_text)
                if (
                    (not assistant_text.strip() or looks_like_plan or halluc)
                    and step < self.max_steps - 1
                    and empty_streak < 2
                ):
                    empty_streak += 1
                    if halluc:
                        # Don't let the model trust its own fake tool output: replace
                        # the assistant message content we just appended.
                        if self.messages and self.messages[-1].role == "assistant":
                            self.messages[-1].content = (
                                "[the previous text contained a fabricated tool_response "
                                "and has been redacted; no tool was actually called]"
                            )
                        nudge = (
                            "Stop. You wrote a fake <tool_response> block. Tools are "
                            "executed by ME, not you. Do not write tool output text. "
                            "Issue a real tool call now (or your final answer)."
                        )
                    elif looks_like_plan:
                        nudge = (
                            "You wrote a plan but did not call a tool. Don't describe "
                            "what you will do -- DO IT. Call the next tool now."
                        )
                    else:
                        nudge = (
                            "Please continue working on the goal. Call a tool now, or "
                            "write your final answer if you're truly done."
                        )
                    self.messages.append(ChatMessage(role="user", content=nudge))
                    continue
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
            empty_streak = 0

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


_HALLUCINATED_TOOL_RESPONSE_RE = None  # lazy compiled below


def _looks_like_hallucinated_tool_output(text: str) -> bool:
    """Detect when the model pretended to call a tool and made up the response.

    Example: ``<tool_response>### `$ read_file` ...</tool_response>``
    """
    if not text:
        return False
    global _HALLUCINATED_TOOL_RESPONSE_RE
    if _HALLUCINATED_TOOL_RESPONSE_RE is None:
        import re as _re

        _HALLUCINATED_TOOL_RESPONSE_RE = _re.compile(
            r"<(tool_response|tool_result|observation|tool_output)\b",
            _re.IGNORECASE,
        )
    return bool(_HALLUCINATED_TOOL_RESPONSE_RE.search(text))


_PLAN_PATTERNS: list[str] = [
    r"\blet'?s\s+(read|run|now|first|edit|fix|check|verify|search|grep|try|see|look)",
    r"\blet\s+me\s+(read|run|now|first|edit|fix|check|verify|search|grep|try|see|look)",
    r"\bi'?ll\s+(read|run|edit|fix|now|first|next|then|check|verify|search|grep|try|see|look|use|call|do|continue|proceed|update|modify|create|write)",
    r"\bi\s+will\s+(read|run|edit|fix|now|first|next|then|check|verify|search|grep|try|see|look|use|call|do|continue|proceed|update|modify|create|write)",
    r"\b(first|next|then|now)\s*,?\s*(i'?ll|i\s+will|let'?s|let\s+me)",
    r"\bto\s+(fix|do|accomplish|solve|address|resolve|complete)\s+this",
    r"\bhere'?s\s+the\s+plan",
    r"\bthe\s+plan\s+is",
    r"\bstep\s*1\b",
    r"^\s*1[.)]\s*(read|run|edit|fix|check|verify|search|grep|try|now|first)",
    r"\bplease\s+confirm",
    r"\bif\s+confirmed",
    r"\bdo\s+you\s+want\s+(me\s+to|to)\b",
    r"\bshould\s+i\b",
]


def _looks_like_plan(text: str) -> bool:
    """Detect when the model wrote a plan instead of calling a tool."""
    if not text:
        return False
    snippet = text.strip().lower()
    if len(snippet) > 1200:
        return False
    import re as _re

    for pat in _PLAN_PATTERNS:
        if _re.search(pat, snippet, _re.IGNORECASE | _re.MULTILINE):
            return True
    return False


def _extract_json_tool_calls(text: str) -> list[ToolCall]:
    """Parse tool calls emitted as JSON in assistant text.

    Recognizes:
      {"name": "...", "arguments": {...}}
      {"name": "...", "parameters": {...}}
      [{"name": "...", "arguments": {...}}, ...]
      ```json\n{...}\n```
      ```tool_call\n{...}\n```
      Multiple JSON blocks separated by <|im_start|> / <|im_end|> (Qwen leak)

    Returns an empty list if nothing tool-call-shaped is found.
    """
    import re
    import uuid

    text = text.strip()
    # Remove explicit role-marker tokens — we treat them as block separators.
    text_no_markers = re.sub(
        r"<\|(im_start|im_end|endoftext)\|>(?:assistant|user|system)?",
        "\n",
        text,
    )

    out: list[ToolCall] = []
    seen: set[tuple[str, str]] = set()

    def add_calls(data: Any) -> None:
        for call in _normalize_tool_call_object(data):
            key = (call.name, json.dumps(call.arguments, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            if not call.id:
                call.id = f"call_{uuid.uuid4().hex[:8]}"
            out.append(call)

    candidates: list[str] = []

    # Strip fenced code blocks (json / tool_call / tool_use / blank fence).
    fence_re = re.compile(
        r"```(?:json|tool_call|tool_use|tool|functions?)?\s*\n?([\s\S]*?)```",
        re.IGNORECASE,
    )
    for m in fence_re.finditer(text_no_markers):
        candidates.append(m.group(1).strip())

    # Strip <tool_call>...</tool_call> tags.
    tag_re = re.compile(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>", re.IGNORECASE)
    for m in tag_re.finditer(text_no_markers):
        candidates.append(m.group(1).strip())

    # The remaining text body — we scan it for all balanced JSON top-level objects.
    candidates.append(text_no_markers)

    for raw in candidates:
        _scan_top_level_json(raw, add_calls)

    return out


def _scan_top_level_json(text: str, sink) -> None:
    """Find every balanced top-level JSON object/array in text and pass parsed value to sink."""
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c not in "{[":
            i += 1
            continue
        end_char = "}" if c == "{" else "]"
        depth = 0
        in_string = False
        escape = False
        j = i
        while j < n:
            ch = text[j]
            if escape:
                escape = False
            elif in_string:
                if ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == c:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                    if depth == 0:
                        chunk = text[i : j + 1]
                        try:
                            data = json.loads(chunk)
                            sink(data)
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                        break
            j += 1
        else:
            # Reached end without closing; advance past this opener.
            i += 1
            continue
        if depth != 0:
            i += 1


def _normalize_tool_call_object(obj: Any) -> list[ToolCall]:
    """Accept various shapes and return ToolCall list."""
    if isinstance(obj, list):
        out: list[ToolCall] = []
        for o in obj:
            out.extend(_normalize_tool_call_object(o))
        return out
    if not isinstance(obj, dict):
        return []
    # OpenAI nested form
    if "function" in obj and isinstance(obj["function"], dict):
        fn = obj["function"]
        name = fn.get("name", "")
        raw_args = fn.get("arguments", {})
        return _build_call(obj.get("id", ""), name, raw_args)
    name = obj.get("name") or obj.get("tool") or obj.get("action")
    args = obj.get("arguments") or obj.get("parameters") or obj.get("args") or obj.get("input")
    if name and isinstance(name, str):
        return _build_call(obj.get("id", ""), name, args if args is not None else {})
    return []


def _build_call(call_id: str, name: str, raw_args: Any) -> list[ToolCall]:
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
            if not isinstance(parsed, dict):
                parsed = {"_arg": parsed}
        except json.JSONDecodeError:
            parsed = {"_raw": raw_args}
    elif isinstance(raw_args, dict):
        parsed = raw_args
    elif raw_args is None:
        parsed = {}
    else:
        parsed = {"_arg": raw_args}
    return [ToolCall(id=call_id, name=name, arguments=parsed)]
