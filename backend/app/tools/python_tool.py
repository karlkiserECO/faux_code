"""Python execution tool — runs code in an isolated subprocess."""

from __future__ import annotations

from typing import Any

from ..sandbox import run_python
from .registry import Tool, ToolContext, ToolResult, register


async def python_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    code = args.get("code", "")
    if not code:
        return ToolResult(ok=False, is_error=True, content="Missing 'code'.")
    timeout = int(args.get("timeout_sec", 30))
    timeout = max(1, min(120, timeout))
    res = await run_python(code, workspace=ctx.workspace, timeout_sec=timeout)
    body = (
        f"### python ({res.duration_sec}s, exit {res.exit_code})\n\n"
        + (f"```\n{res.stdout}\n```\n" if res.stdout else "")
        + (f"**stderr**\n```\n{res.stderr}\n```\n" if res.stderr else "")
    )
    if res.timed_out:
        body += "\n_TIMEOUT_\n"
    return ToolResult(ok=res.ok, content=body, data=res.to_dict(), is_error=not res.ok)


register(
    Tool(
        name="python",
        description=(
            "Run a Python 3 snippet in an isolated subprocess. Stdout/stderr are "
            "captured. Use for calculations, parsing, quick scripting. 30s default timeout."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source to execute."},
                "timeout_sec": {"type": "integer", "default": 30, "minimum": 1, "maximum": 120},
            },
            "required": ["code"],
        },
        writes=False,
        handler=python_handler,
    )
)
