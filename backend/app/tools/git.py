"""Git inspection tools — status, diff, log. Read-only and path-jailed."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from ..sandbox import run_shell
from .registry import Tool, ToolContext, ToolResult, register


def _workspace(ctx: ToolContext) -> Path:
    if ctx and ctx.workspace:
        return ctx.workspace.resolve()
    from ..settings import get_settings

    return get_settings().workspace_root.resolve()


def _resolve_inside(ws: Path, rel_or_abs: str) -> Path:
    """Resolve a user-provided path strictly inside the workspace."""
    if not rel_or_abs:
        return ws
    if Path(rel_or_abs).is_absolute():
        p = Path(rel_or_abs).resolve()
    else:
        p = (ws / rel_or_abs).resolve()
    try:
        p.relative_to(ws)
    except ValueError as e:
        raise PermissionError(f"Path escapes workspace: {p}") from e
    return p


def _classify(xy: str) -> str:
    """Map porcelain v1 status XY codes to a human category."""
    if xy == "??":
        return "untracked"
    if xy == "!!":
        return "ignored"
    if "U" in xy or xy in {"AA", "DD"}:
        return "conflicted"
    if "R" in xy:
        return "renamed"
    if "C" in xy:
        return "copied"
    if "D" in xy:
        return "deleted"
    if "A" in xy:
        return "added"
    if "M" in xy or "T" in xy:
        return "modified"
    return "other"


def _format_status(branch_line: str, files: list[dict]) -> str:
    branch = "(unknown)"
    extra = ""
    if branch_line.startswith("## "):
        rest = branch_line[3:]
        if rest.startswith("No commits yet on "):
            branch = rest[len("No commits yet on ") :].strip()
            extra = " (no commits yet)"
        else:
            head, _, info = rest.partition(" ")
            branch = head.split("...", 1)[0] if "..." in head else head
            info = info.strip()
            if info.startswith("[") and info.endswith("]"):
                extra = f" ({info[1:-1]})"

    sections: dict[str, list[str]] = {}
    for f in files:
        sections.setdefault(f["state"], []).append(f["path"])
    order = [
        "modified",
        "added",
        "deleted",
        "renamed",
        "copied",
        "conflicted",
        "untracked",
        "ignored",
        "other",
    ]
    parts = [f"### Branch: {branch}{extra}", ""]
    any_files = False
    for key in order:
        items = sections.get(key)
        if not items:
            continue
        any_files = True
        parts.append(f"{key.capitalize()}:")
        parts.extend(f"- {p}" for p in items)
        parts.append("")
    if not any_files:
        parts.append("(working tree clean)")
    return "\n".join(parts).rstrip() + "\n"


def _is_not_a_repo(stderr: str) -> bool:
    s = (stderr or "").lower()
    return "not a git repository" in s or "fatal: not a git repository" in s


async def git_status_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    ws = _workspace(ctx)
    res = await run_shell("git status --porcelain=v1 -b", workspace=ws)
    if not res.ok:
        msg = (res.stderr or res.stdout or "").strip()
        if _is_not_a_repo(msg):
            return ToolResult(
                ok=False,
                is_error=True,
                content=f"Not a git repository: `{ws}`.",
                data=res.to_dict(),
            )
        return ToolResult(
            ok=False,
            is_error=True,
            content=f"git status failed:\n```\n{msg or '(no output)'}\n```",
            data=res.to_dict(),
        )

    lines = res.stdout.splitlines()
    branch_line = lines[0] if lines else ""
    files: list[dict] = []
    for line in lines[1:]:
        if len(line) < 3:
            continue
        xy = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append({"xy": xy, "state": _classify(xy), "path": path})

    return ToolResult(
        ok=True,
        content=_format_status(branch_line, files),
        data={"branch_line": branch_line, "files": files},
    )


async def git_diff_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    ws = _workspace(ctx)
    staged = bool(args.get("staged", False))
    path = (args.get("path") or "").strip()
    try:
        max_lines = int(args.get("max_lines", 1000))
    except (TypeError, ValueError):
        max_lines = 1000
    max_lines = max(1, min(100000, max_lines))

    if path:
        try:
            _resolve_inside(ws, path)
        except PermissionError as e:
            return ToolResult(ok=False, is_error=True, content=str(e))

    cmd_parts = ["git", "--no-pager", "diff"]
    if staged:
        cmd_parts.append("--cached")
    if path:
        cmd_parts.append("--")
        cmd_parts.append(path)
    cmd = " ".join(shlex.quote(p) for p in cmd_parts)
    res = await run_shell(cmd, workspace=ws)
    if not res.ok:
        msg = (res.stderr or res.stdout or "").strip()
        if _is_not_a_repo(msg):
            return ToolResult(
                ok=False,
                is_error=True,
                content=f"Not a git repository: `{ws}`.",
                data=res.to_dict(),
            )
        return ToolResult(
            ok=False,
            is_error=True,
            content=f"git diff failed:\n```\n{msg or '(no output)'}\n```",
            data=res.to_dict(),
        )

    out_lines = (res.stdout or "").splitlines()
    truncated = False
    if len(out_lines) > max_lines:
        out_lines = out_lines[:max_lines]
        truncated = True
    body = "\n".join(out_lines)
    title = (
        "### git diff"
        + (" --cached" if staged else "")
        + (f" -- {path}" if path else "")
    )
    if not body.strip():
        return ToolResult(
            ok=True, content=f"{title}\n\n(no changes)", data={"empty": True}
        )
    suffix = f"\n\n_…[truncated at {max_lines} lines]_" if truncated else ""
    return ToolResult(
        ok=True,
        content=f"{title}\n\n```diff\n{body}\n```{suffix}",
        data={"truncated": truncated, "lines": len(out_lines)},
    )


async def git_log_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    ws = _workspace(ctx)
    try:
        limit = int(args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(100, limit))
    path = (args.get("path") or "").strip()

    if path:
        try:
            _resolve_inside(ws, path)
        except PermissionError as e:
            return ToolResult(ok=False, is_error=True, content=str(e))

    cmd_parts = ["git", "--no-pager", "log", "--oneline", "-n", str(limit)]
    if path:
        cmd_parts.append("--")
        cmd_parts.append(path)
    cmd = " ".join(shlex.quote(p) for p in cmd_parts)
    res = await run_shell(cmd, workspace=ws)
    if not res.ok:
        msg = (res.stderr or res.stdout or "").strip()
        low = msg.lower()
        if _is_not_a_repo(msg):
            return ToolResult(
                ok=False,
                is_error=True,
                content=f"Not a git repository: `{ws}`.",
                data=res.to_dict(),
            )
        if (
            "does not have any commits yet" in low
            or "bad default revision" in low
            or "ambiguous argument 'head'" in low
        ):
            return ToolResult(
                ok=True,
                content="### git log\n\n(no commits yet)",
                data={"commits": []},
            )
        return ToolResult(
            ok=False,
            is_error=True,
            content=f"git log failed:\n```\n{msg or '(no output)'}\n```",
            data=res.to_dict(),
        )

    body = (res.stdout or "").strip()
    if not body:
        return ToolResult(
            ok=True, content="### git log\n\n(no commits)", data={"commits": []}
        )

    commits = []
    for line in body.splitlines():
        if not line.strip():
            continue
        sha, _, subject = line.partition(" ")
        commits.append({"sha": sha, "subject": subject})

    title = "### git log" + (f" -- {path}" if path else "")
    return ToolResult(
        ok=True,
        content=f"{title}\n\n```\n{body}\n```",
        data={"commits": commits},
    )


register(
    Tool(
        name="git_status",
        description=(
            "Show git status of the workspace: current branch, modified/added/"
            "deleted/untracked files."
        ),
        parameters={"type": "object", "properties": {}},
        writes=False,
        handler=git_status_handler,
    )
)

register(
    Tool(
        name="git_diff",
        description=(
            "Show git diff for the workspace. By default shows unstaged changes; "
            "set staged=true for the staged-only diff. Optionally limit to a path."
        ),
        parameters={
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "default": False,
                    "description": "Show staged diff only.",
                },
                "path": {
                    "type": "string",
                    "default": "",
                    "description": "Limit to this path.",
                },
                "max_lines": {"type": "integer", "default": 1000},
            },
        },
        writes=False,
        handler=git_diff_handler,
    )
)

register(
    Tool(
        name="git_log",
        description="Show recent git commits as one-line summaries.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
                "path": {"type": "string", "default": ""},
            },
        },
        writes=False,
        handler=git_log_handler,
    )
)
