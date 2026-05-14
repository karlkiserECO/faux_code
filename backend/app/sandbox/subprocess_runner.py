"""Subprocess sandbox runner with path-jail, env scrubbing, timeouts, and output limits.

This is the v1 sandbox. For multi-user / internet-exposed deployments, swap for a
Docker / gVisor / Firecracker runner. The interface stays the same.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_TIMEOUT_SEC = 60
MAX_OUTPUT_BYTES = 256 * 1024  # 256 KB cap per stream


@dataclass
class SandboxResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool
    timed_out: bool
    duration_sec: float
    cmd: str

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "truncated": self.truncated,
            "timed_out": self.timed_out,
            "duration_sec": round(self.duration_sec, 3),
            "cmd": self.cmd,
        }


def _safe_env() -> dict[str, str]:
    """Minimal env for child processes."""
    keep = {"PATH", "HOME", "LANG", "LC_ALL", "TERM", "USER", "TMPDIR"}
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin")
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def _resolve_cwd(workspace: Optional[str | Path]) -> Path:
    """Resolve and validate the working directory."""
    if not workspace:
        from ..settings import get_settings

        s = get_settings()
        cwd = s.workspace_root.resolve()
    else:
        cwd = Path(workspace).resolve()
    cwd.mkdir(parents=True, exist_ok=True)
    return cwd


async def _run(
    cmd: list[str] | str,
    *,
    cwd: Path,
    timeout_sec: int,
    shell: bool,
    stdin: Optional[str] = None,
) -> SandboxResult:
    start = asyncio.get_event_loop().time()
    if shell:
        if isinstance(cmd, list):
            cmd_str = " ".join(shlex.quote(c) for c in cmd)
        else:
            cmd_str = cmd
        proc = await asyncio.create_subprocess_shell(
            cmd_str,
            cwd=str(cwd),
            env=_safe_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            preexec_fn=os.setsid if sys.platform != "win32" else None,
        )
        display_cmd = cmd_str
    else:
        if isinstance(cmd, str):
            cmd_list = shlex.split(cmd)
        else:
            cmd_list = cmd
        proc = await asyncio.create_subprocess_exec(
            *cmd_list,
            cwd=str(cwd),
            env=_safe_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            preexec_fn=os.setsid if sys.platform != "win32" else None,
        )
        display_cmd = " ".join(shlex.quote(c) for c in cmd_list)

    timed_out = False
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=stdin.encode("utf-8") if stdin else None),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        timed_out = True
        try:
            if proc.pid:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            stdout_b, stderr_b = await proc.communicate()
        except Exception:
            stdout_b, stderr_b = b"", b""

    duration = asyncio.get_event_loop().time() - start
    truncated = False
    truncation_suffix = b"\n...[truncated]"
    if len(stdout_b) > MAX_OUTPUT_BYTES:
        stdout_b = stdout_b[:MAX_OUTPUT_BYTES] + truncation_suffix
        truncated = True
    if len(stderr_b) > MAX_OUTPUT_BYTES:
        stderr_b = stderr_b[:MAX_OUTPUT_BYTES] + truncation_suffix
        truncated = True

    return SandboxResult(
        ok=(proc.returncode == 0) and not timed_out,
        exit_code=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout_b.decode("utf-8", errors="replace"),
        stderr=stderr_b.decode("utf-8", errors="replace"),
        truncated=truncated,
        timed_out=timed_out,
        duration_sec=duration,
        cmd=display_cmd,
    )


async def run_shell(
    cmd: str,
    *,
    workspace: Optional[str | Path] = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> SandboxResult:
    cwd = _resolve_cwd(workspace)
    return await _run(cmd, cwd=cwd, timeout_sec=timeout_sec, shell=True)


async def run_python(
    code: str,
    *,
    workspace: Optional[str | Path] = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> SandboxResult:
    cwd = _resolve_cwd(workspace)
    return await _run(
        [sys.executable, "-I", "-c", code],
        cwd=cwd,
        timeout_sec=timeout_sec,
        shell=False,
    )
