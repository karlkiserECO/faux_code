"""Shell tool — wraps the sandbox runner with approval gating."""

from __future__ import annotations

from typing import Any

from ..sandbox import run_shell
from .registry import Tool, ToolContext, ToolResult, register


async def shell_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    cmd = args.get("command", "").strip()
    if not cmd:
        return ToolResult(ok=False, is_error=True, content="Missing 'command'.")
    timeout = int(args.get("timeout_sec", 60))
    timeout = max(1, min(300, timeout))

    if ctx.approval_mode in ("require_for_writes", "require_all") and ctx.request_approval:
        ok = await ctx.request_approval("shell", {"command": cmd, "timeout_sec": timeout})
        if not ok:
            return ToolResult(ok=False, is_error=True, content="Approval denied.")

    res = await run_shell(cmd, workspace=ctx.workspace, timeout_sec=timeout)
    body = (
        f"### `$ {res.cmd}`\n"
        f"exit_code: {res.exit_code} • duration: {res.duration_sec}s"
        + (" • TIMEOUT" if res.timed_out else "")
        + (" • truncated" if res.truncated else "")
        + "\n\n"
        + (f"**stdout**\n```\n{res.stdout or '(empty)'}\n```\n" if res.stdout or not res.stderr else "")
        + (f"**stderr**\n```\n{res.stderr}\n```\n" if res.stderr else "")
    )
    return ToolResult(ok=res.ok, content=body, data=res.to_dict(), is_error=not res.ok)


register(
    Tool(
        name="shell",
        description=(
            "Execute a shell command in the workspace. Use for git, ls, cat, grep, "
            "package managers, build commands, and tests. Sandboxed with a 60s default "
            "timeout. May require approval."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command line."},
                "timeout_sec": {"type": "integer", "default": 60, "minimum": 1, "maximum": 300},
            },
            "required": ["command"],
        },
        writes=True,
        handler=shell_handler,
    )
)
