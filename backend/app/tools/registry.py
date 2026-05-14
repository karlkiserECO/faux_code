"""Tool registry — declarative tool definitions + executors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from ..providers import ToolDef


@dataclass
class ToolContext:
    """Per-call context for tool executors."""

    workspace: Optional[Path] = None
    approval_mode: str = "auto"  # auto | require_for_writes | require_all
    request_approval: Optional[Callable[[str, dict[str, Any]], Awaitable[bool]]] = None


@dataclass
class ToolResult:
    ok: bool
    content: str = ""  # human/agent-readable result text (markdown allowed)
    data: dict[str, Any] = field(default_factory=dict)
    is_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "content": self.content,
            "data": self.data,
            "is_error": self.is_error,
        }


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    writes: bool
    handler: Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult]]

    def to_def(self) -> ToolDef:
        return ToolDef(name=self.name, description=self.description, parameters=self.parameters)


_TOOLS: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    _TOOLS[tool.name] = tool
    return tool


def get_tool(name: str) -> Tool:
    if name not in _TOOLS:
        raise KeyError(f"Unknown tool: {name}")
    return _TOOLS[name]


def list_tools() -> list[Tool]:
    return list(_TOOLS.values())


def tool_definitions(names: list[str] | None = None) -> list[ToolDef]:
    if names is None:
        return [t.to_def() for t in _TOOLS.values()]
    return [_TOOLS[n].to_def() for n in names if n in _TOOLS]
