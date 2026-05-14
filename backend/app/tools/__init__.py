from .registry import (
    Tool,
    ToolContext,
    ToolResult,
    get_tool,
    list_tools,
    register,
    tool_definitions,
)

# Eagerly import to register all built-in tools.
from . import web_search, web_fetch, fs as _fs, shell as _shell, python_tool, rag_tool  # noqa: F401

__all__ = [
    "Tool",
    "ToolContext",
    "ToolResult",
    "get_tool",
    "list_tools",
    "register",
    "tool_definitions",
]
