"""File-system tools — list, read, write, edit. All path-jailed to the workspace."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import aiofiles

from ..settings import get_settings
from .registry import Tool, ToolContext, ToolResult, register

MAX_READ_BYTES = 512 * 1024
MAX_LIST_ENTRIES = 500


def _workspace(ctx: ToolContext) -> Path:
    if ctx and ctx.workspace:
        return ctx.workspace.resolve()
    return get_settings().workspace_root.resolve()


def _resolve_inside(ws: Path, rel_or_abs: str) -> Path:
    """Resolve a user-provided path strictly inside the workspace."""
    if not rel_or_abs:
        return ws
    p = (ws / rel_or_abs).resolve() if not Path(rel_or_abs).is_absolute() else Path(rel_or_abs).resolve()
    try:
        p.relative_to(ws)
    except ValueError as e:
        raise PermissionError(f"Path escapes workspace: {p}") from e
    return p


async def _approve_if_needed(ctx: ToolContext, op: str, args: dict[str, Any]) -> ToolResult | None:
    if ctx.approval_mode == "require_all" or ctx.approval_mode == "require_for_writes":
        if ctx.request_approval is not None:
            ok = await ctx.request_approval(op, args)
            if not ok:
                return ToolResult(
                    ok=False, is_error=True, content=f"Approval denied for {op}."
                )
    return None


async def list_dir_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    ws = _workspace(ctx)
    rel = args.get("path", "")
    try:
        target = _resolve_inside(ws, rel)
    except PermissionError as e:
        return ToolResult(ok=False, is_error=True, content=str(e))
    if not target.exists():
        return ToolResult(ok=False, is_error=True, content=f"Not found: {target}")
    if target.is_file():
        return await read_file_handler({"path": rel}, ctx)
    entries = []
    try:
        for i, p in enumerate(sorted(target.iterdir())):
            if i >= MAX_LIST_ENTRIES:
                break
            try:
                size = p.stat().st_size if p.is_file() else None
            except OSError:
                size = None
            entries.append(
                {
                    "name": p.name,
                    "is_dir": p.is_dir(),
                    "size": size,
                    "path": str(p.relative_to(ws)),
                }
            )
    except PermissionError as e:
        return ToolResult(ok=False, is_error=True, content=f"Permission error: {e}")
    listing = "\n".join(
        f"{'📁' if e['is_dir'] else '📄'} {e['path']}"
        + (f"  ({e['size']} bytes)" if e["size"] is not None else "")
        for e in entries
    )
    return ToolResult(
        ok=True,
        content=f"### `{target.relative_to(ws) or '.'}`\n\n{listing or '(empty directory)'}",
        data={"path": str(target.relative_to(ws)), "entries": entries},
    )


async def read_file_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    ws = _workspace(ctx)
    rel = args.get("path") or ""
    if not rel:
        return ToolResult(ok=False, is_error=True, content="Missing 'path'.")
    try:
        target = _resolve_inside(ws, rel)
    except PermissionError as e:
        return ToolResult(ok=False, is_error=True, content=str(e))
    if not target.exists() or not target.is_file():
        return ToolResult(ok=False, is_error=True, content=f"Not a file: {target}")
    try:
        size = target.stat().st_size
        async with aiofiles.open(target, "rb") as f:
            blob = await f.read(MAX_READ_BYTES + 1)
        truncated = len(blob) > MAX_READ_BYTES
        text = blob[:MAX_READ_BYTES].decode("utf-8", errors="replace")
        suffix = "\n\n…[truncated]" if truncated else ""
        return ToolResult(
            ok=True,
            content=f"### `{target.relative_to(ws)}` ({size} bytes)\n\n```\n{text}{suffix}\n```",
            data={
                "path": str(target.relative_to(ws)),
                "size": size,
                "truncated": truncated,
                "text": text,
            },
        )
    except Exception as e:
        return ToolResult(ok=False, is_error=True, content=f"Read error: {e}")


async def write_file_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    rel = args.get("path") or ""
    content = args.get("content", "")
    if not rel:
        return ToolResult(ok=False, is_error=True, content="Missing 'path'.")
    if not isinstance(content, str):
        return ToolResult(ok=False, is_error=True, content="'content' must be a string.")
    denied = await _approve_if_needed(ctx, "write_file", args)
    if denied:
        return denied
    ws = _workspace(ctx)
    try:
        target = _resolve_inside(ws, rel)
    except PermissionError as e:
        return ToolResult(ok=False, is_error=True, content=str(e))
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with aiofiles.open(target, "w", encoding="utf-8") as f:
            await f.write(content)
    except Exception as e:
        return ToolResult(ok=False, is_error=True, content=f"Write error: {e}")
    return ToolResult(
        ok=True,
        content=f"Wrote {len(content)} chars to `{target.relative_to(ws)}`.",
        data={"path": str(target.relative_to(ws)), "size": len(content)},
    )


async def edit_file_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Search-and-replace edit. `find` must be unique unless `replace_all`."""
    rel = args.get("path") or ""
    find = args.get("find", "")
    replace = args.get("replace", "")
    replace_all = bool(args.get("replace_all", False))
    if not rel or not find:
        return ToolResult(ok=False, is_error=True, content="Need 'path' and 'find'.")
    denied = await _approve_if_needed(ctx, "edit_file", args)
    if denied:
        return denied
    ws = _workspace(ctx)
    try:
        target = _resolve_inside(ws, rel)
    except PermissionError as e:
        return ToolResult(ok=False, is_error=True, content=str(e))
    if not target.exists() or not target.is_file():
        return ToolResult(ok=False, is_error=True, content=f"Not a file: {target}")
    try:
        async with aiofiles.open(target, "r", encoding="utf-8", errors="replace") as f:
            text = await f.read()
    except Exception as e:
        return ToolResult(ok=False, is_error=True, content=f"Read error: {e}")
    count = text.count(find)
    if count == 0:
        return ToolResult(ok=False, is_error=True, content="'find' not found in file.")
    if count > 1 and not replace_all:
        return ToolResult(
            ok=False,
            is_error=True,
            content=f"'find' is not unique ({count} matches). Pass replace_all=true or use a longer snippet.",
        )
    new_text = text.replace(find, replace) if replace_all else text.replace(find, replace, 1)
    try:
        async with aiofiles.open(target, "w", encoding="utf-8") as f:
            await f.write(new_text)
    except Exception as e:
        return ToolResult(ok=False, is_error=True, content=f"Write error: {e}")
    return ToolResult(
        ok=True,
        content=f"Edited `{target.relative_to(ws)}` ({count if replace_all else 1} replacement(s)).",
        data={"path": str(target.relative_to(ws)), "replacements": count if replace_all else 1},
    )


async def grep_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Simple substring search across workspace files."""
    import re

    pattern = args.get("pattern", "")
    rel = args.get("path", "")
    ignore_case = bool(args.get("ignore_case", True))
    max_hits = int(args.get("max_hits", 100))
    if not pattern:
        return ToolResult(ok=False, is_error=True, content="Missing 'pattern'.")
    ws = _workspace(ctx)
    try:
        root = _resolve_inside(ws, rel)
    except PermissionError as e:
        return ToolResult(ok=False, is_error=True, content=str(e))
    if root.is_file():
        files = [root]
    else:
        files = [p for p in root.rglob("*") if p.is_file()]

    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error:
        rx = re.compile(re.escape(pattern), flags)
    hits: list[dict[str, Any]] = []
    for f in files:
        if any(part.startswith(".") and part not in {".", ".."} for part in f.parts):
            continue
        try:
            with open(f, "r", encoding="utf-8", errors="ignore") as h:
                for ln, line in enumerate(h, 1):
                    if rx.search(line):
                        hits.append(
                            {
                                "path": str(f.relative_to(ws)),
                                "line": ln,
                                "text": line.rstrip("\n")[:300],
                            }
                        )
                        if len(hits) >= max_hits:
                            break
        except Exception:
            continue
        if len(hits) >= max_hits:
            break
    if not hits:
        return ToolResult(ok=True, content="No matches.")
    lines = [f"### grep `{pattern}` — {len(hits)} hits", ""]
    for h in hits:
        lines.append(f"`{h['path']}:{h['line']}` — {h['text']}")
    return ToolResult(ok=True, content="\n".join(lines), data={"hits": hits})


register(
    Tool(
        name="list_dir",
        description="List entries in a workspace directory (or read a file path).",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative directory path. Empty for root.",
                    "default": "",
                }
            },
        },
        writes=False,
        handler=list_dir_handler,
    )
)

register(
    Tool(
        name="read_file",
        description="Read a UTF-8 text file from the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path."}
            },
            "required": ["path"],
        },
        writes=False,
        handler=read_file_handler,
    )
)

register(
    Tool(
        name="write_file",
        description=(
            "Write a UTF-8 text file. Overwrites if it exists. Workspace-jailed. May "
            "require approval depending on the run's approval_mode."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path."},
                "content": {"type": "string", "description": "Full file content."},
            },
            "required": ["path", "content"],
        },
        writes=True,
        handler=write_file_handler,
    )
)

register(
    Tool(
        name="edit_file",
        description=(
            "Search-and-replace edit in a file. By default, 'find' must be unique. "
            "Pass replace_all=true to replace all occurrences."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "find": {"type": "string"},
                "replace": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["path", "find", "replace"],
        },
        writes=True,
        handler=edit_file_handler,
    )
)

register(
    Tool(
        name="grep",
        description="Search workspace files with a regex pattern.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "default": ""},
                "ignore_case": {"type": "boolean", "default": True},
                "max_hits": {"type": "integer", "default": 100},
            },
            "required": ["pattern"],
        },
        writes=False,
        handler=grep_handler,
    )
)
