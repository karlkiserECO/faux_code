"""Apply unified-diff patches to the workspace, path-jailed.

Strategy: write the patch to a temp file inside the workspace, try `git apply`
first (preferred — it handles binary, mode changes, renames, and `--whitespace`
fixups), then fall back to `patch -pN`. Before running anything, we parse the
patch and reject it if any target path resolves outside the workspace.
"""

from __future__ import annotations

import re
import shlex
import tempfile
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


def _strip_components(path: str, n: int) -> str:
    """Strip the leading N path components, like `patch -pN` does."""
    if path == "/dev/null":
        return path
    parts = path.split("/")
    if n >= len(parts):
        return ""
    return "/".join(parts[n:])


_HEADER_RE = re.compile(r"^(?:---|\+\+\+) (.+?)(?:\t.*)?$")
_DIFF_GIT_RE = re.compile(r"^diff --git (\S+) (\S+)$")


def _extract_targets(patch: str, strip: int) -> list[str]:
    """Extract every concrete file path referenced by the patch."""
    targets: list[str] = []
    for raw in patch.splitlines():
        line = raw.rstrip("\r")
        m = _HEADER_RE.match(line)
        if m:
            p = m.group(1).strip()
            if p == "/dev/null":
                continue
            stripped = _strip_components(p, strip)
            if stripped:
                targets.append(stripped)
            continue
        m = _DIFF_GIT_RE.match(line)
        if m:
            for p in (m.group(1), m.group(2)):
                stripped = _strip_components(p, strip)
                if stripped:
                    targets.append(stripped)
    return targets


async def apply_patch_handler(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    patch = args.get("patch", "")
    if not isinstance(patch, str) or not patch.strip():
        return ToolResult(ok=False, is_error=True, content="Missing or empty 'patch'.")

    try:
        strip = int(args.get("strip", 1))
    except (TypeError, ValueError):
        return ToolResult(ok=False, is_error=True, content="'strip' must be an integer.")
    if strip < 0:
        return ToolResult(ok=False, is_error=True, content="'strip' must be >= 0.")

    if ctx.approval_mode in ("require_for_writes", "require_all") and ctx.request_approval:
        approved = await ctx.request_approval("apply_patch", args)
        if not approved:
            return ToolResult(
                ok=False, is_error=True, content="Approval denied for apply_patch."
            )

    ws = _workspace(ctx)

    try:
        targets = _extract_targets(patch, strip)
        for t in targets:
            _resolve_inside(ws, t)
    except PermissionError as e:
        return ToolResult(
            ok=False,
            is_error=True,
            content=f"Patch rejected: {e}",
            data={"targets": targets},
        )

    ws.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".diff",
        prefix=".faux_apply_patch_",
        dir=str(ws),
        delete=False,
        encoding="utf-8",
    ) as fp:
        fp.write(patch)
        if not patch.endswith("\n"):
            fp.write("\n")
        patch_file = Path(fp.name)

    try:
        rel_patch = patch_file.relative_to(ws)
        quoted = shlex.quote(str(rel_patch))

        git_cmd = (
            f"git apply --whitespace=fix --unidiff-zero -p{strip} {quoted}"
        )
        git_res = await run_shell(git_cmd, workspace=ws)
        if git_res.ok:
            unique = sorted({t for t in targets if t})
            return ToolResult(
                ok=True,
                content=(
                    f"Applied patch via `git apply` "
                    f"({len(unique)} file path(s) referenced).\n\n"
                    + ("\n".join(f"- {p}" for p in unique) if unique else "")
                ),
                data={
                    "tool": "git apply",
                    "exit_code": git_res.exit_code,
                    "targets": unique,
                },
            )

        patch_cmd = f"patch -p{strip} -i {quoted}"
        patch_res = await run_shell(patch_cmd, workspace=ws)
        if patch_res.ok:
            unique = sorted({t for t in targets if t})
            return ToolResult(
                ok=True,
                content=(
                    f"Applied patch via `patch -p{strip}` "
                    f"({len(unique)} file path(s) referenced).\n\n"
                    + ("\n".join(f"- {p}" for p in unique) if unique else "")
                ),
                data={
                    "tool": "patch",
                    "exit_code": patch_res.exit_code,
                    "stdout": patch_res.stdout,
                    "targets": unique,
                },
            )

        git_msg = (git_res.stderr or git_res.stdout or "(no output)").strip()
        patch_msg = (patch_res.stderr or patch_res.stdout or "(no output)").strip()
        return ToolResult(
            ok=False,
            is_error=True,
            content=(
                "Failed to apply patch with both `git apply` and `patch`.\n\n"
                f"**git apply** (exit {git_res.exit_code}):\n```\n{git_msg}\n```\n\n"
                f"**patch -p{strip}** (exit {patch_res.exit_code}):\n```\n{patch_msg}\n```"
            ),
            data={
                "git_apply_exit": git_res.exit_code,
                "git_apply_stderr": git_res.stderr,
                "patch_exit": patch_res.exit_code,
                "patch_stderr": patch_res.stderr,
            },
        )
    finally:
        try:
            patch_file.unlink()
        except OSError:
            pass


register(
    Tool(
        name="apply_patch",
        description=(
            "Apply a unified-diff patch to files in the workspace. Useful for "
            "proposing multi-file changes as a single atomic edit. Use this "
            "instead of write_file when changes affect multiple files or many "
            "small hunks."
        ),
        parameters={
            "type": "object",
            "properties": {
                "patch": {"type": "string", "description": "Unified diff text."},
                "strip": {
                    "type": "integer",
                    "default": 1,
                    "description": "Strip N leading path components (like -pN).",
                },
            },
            "required": ["patch"],
        },
        writes=True,
        handler=apply_patch_handler,
    )
)
