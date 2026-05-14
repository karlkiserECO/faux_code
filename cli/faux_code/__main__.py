"""faux-code CLI — terminal interface to the local backend.

Subcommands:
- chat       one-shot or interactive chat
- agent      run an agent goal in the current directory
- serve      start the backend (alias for faux-code-server)
- models     list available models
- pull       pull a local Ollama model

The CLI talks to a running backend via HTTP. If the backend isn't running, it
auto-starts one on first use.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.spinner import Spinner

app = typer.Typer(
    name="faux-code",
    help="Self-hosted multi-provider AI chat and agentic coding workbench.",
    no_args_is_help=False,
    add_completion=False,
)

console = Console()

DEFAULT_BASE = os.environ.get("FAUX_BASE", "http://127.0.0.1:8765")


def _api() -> str:
    return DEFAULT_BASE.rstrip("/")


async def _is_alive(base: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.5) as c:
            r = await c.get(f"{base}/healthz")
            return r.status_code == 200
    except Exception:
        return False


def _ensure_backend() -> Optional[subprocess.Popen]:
    """Auto-launch backend if not running. Returns the Popen if we spawned it."""
    if asyncio.run(_is_alive(_api())):
        return None
    console.print(f"[yellow]Backend not running at {_api()}, starting one…[/yellow]")
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.app.main"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        if asyncio.run(_is_alive(_api())):
            console.print("[green]Backend ready.[/green]")
            return proc
        time.sleep(0.25)
    console.print("[red]Backend failed to start. Check `python -m backend.app.main`.[/red]")
    raise typer.Exit(1)


async def _stream_chat(
    base: str,
    messages: list[dict],
    *,
    provider: Optional[str],
    model: str,
    system_prompt: Optional[str],
    persist: bool = False,
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "messages": messages,
        "system_prompt": system_prompt,
        "persist": persist,
    }
    out = ""
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{base}/v1/chat/completions", json=payload) as r:
            if r.status_code >= 400:
                body = (await r.aread()).decode("utf-8", "ignore")
                raise RuntimeError(f"HTTP {r.status_code}: {body[:500]}")
            event = "message"
            data_lines: list[str] = []
            async for line in r.aiter_lines():
                if line == "":
                    raw = "\n".join(data_lines)
                    if event == "delta":
                        out += raw
                    elif event == "error":
                        raise RuntimeError(raw)
                    elif event == "done":
                        return out
                    event = "message"
                    data_lines = []
                    continue
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
    return out


async def _print_stream(
    base: str,
    messages: list[dict],
    *,
    provider: Optional[str],
    model: str,
    system_prompt: Optional[str],
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "messages": messages,
        "system_prompt": system_prompt,
        "persist": False,
    }
    out = ""
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{base}/v1/chat/completions", json=payload) as r:
            if r.status_code >= 400:
                body = (await r.aread()).decode("utf-8", "ignore")
                raise RuntimeError(f"HTTP {r.status_code}: {body[:500]}")
            event = "message"
            data_lines: list[str] = []
            async for line in r.aiter_lines():
                if line == "":
                    raw = "\n".join(data_lines)
                    if event == "delta":
                        out += raw
                        console.print(raw, end="", soft_wrap=True)
                    elif event == "error":
                        console.print(f"\n[red]Error: {raw}[/red]")
                    elif event == "done":
                        console.print()
                        return out
                    event = "message"
                    data_lines = []
                    continue
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
    return out


async def _stream_agent(base: str, run_id: str) -> None:
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET", f"{base}/v1/agents/runs/{run_id}/events") as r:
            event = "message"
            data_lines: list[str] = []
            async for line in r.aiter_lines():
                if line == "":
                    raw = "\n".join(data_lines)
                    data: dict | str
                    try:
                        data = json.loads(raw) if raw else {}
                    except json.JSONDecodeError:
                        data = raw
                    if event == "assistant_delta" and isinstance(data, dict):
                        console.print(data.get("delta", ""), end="", soft_wrap=True)
                    elif event == "tool_call" and isinstance(data, dict):
                        args = data.get("arguments", {})
                        console.print(
                            f"\n[cyan]→ {data.get('name')}[/cyan] {shlex.quote(json.dumps(args))[:200]}"
                        )
                    elif event == "tool_result" and isinstance(data, dict):
                        ok = not data.get("is_error", False)
                        marker = "[green]✓[/green]" if ok else "[red]✗[/red]"
                        content = data.get("content", "")
                        snippet = content.replace("\n", " ")[:160]
                        console.print(f"{marker} {data.get('name')}: {snippet}")
                    elif event == "finished" and isinstance(data, dict):
                        console.print(
                            f"\n[bold green]Completed in {data.get('steps_taken')} step(s).[/bold green]"
                        )
                    elif event == "error" and isinstance(data, dict):
                        console.print(f"\n[red]Error: {data.get('message')}[/red]")
                    elif event == "done":
                        return
                    event = "message"
                    data_lines = []
                    continue
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())


@app.command()
def chat(
    message: Optional[str] = typer.Argument(None, help="Single message; omit for interactive."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
    model: str = typer.Option("llama3.2:3b", "--model", "-m"),
    system: Optional[str] = typer.Option(None, "--system", "-s"),
):
    """Chat with the local AI (one-shot or interactive)."""
    _ensure_backend()
    base = _api()

    if message:
        msgs = [{"role": "user", "content": message}]
        asyncio.run(_print_stream(base, msgs, provider=provider, model=model, system_prompt=system))
        return

    # Interactive
    history: list[dict] = []
    console.print(
        Panel.fit(
            f"[bold]faux_code chat[/bold]\nProvider: {provider or 'auto'} • Model: {model}\nType :exit to quit, :clear to reset, :model <name> to switch model.",
            border_style="cyan",
        )
    )
    while True:
        try:
            msg = Prompt.ask("[bold cyan]you[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            return
        msg = msg.strip()
        if not msg:
            continue
        if msg in (":exit", ":quit"):
            return
        if msg == ":clear":
            history.clear()
            console.print("[dim]history cleared[/dim]")
            continue
        if msg.startswith(":model "):
            model = msg.split(" ", 1)[1].strip()
            console.print(f"[dim]model -> {model}[/dim]")
            continue
        history.append({"role": "user", "content": msg})
        console.print("[bold green]assistant[/bold green]:", end=" ")
        try:
            text = asyncio.run(
                _print_stream(base, history, provider=provider, model=model, system_prompt=system)
            )
        except Exception as e:
            console.print(f"\n[red]{e}[/red]")
            continue
        history.append({"role": "assistant", "content": text})


@app.command()
def agent(
    goal: str = typer.Argument(..., help="What should the agent do?"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
    model: str = typer.Option("llama3.2:3b", "--model", "-m"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory (default: cwd)."),
    approval_mode: str = typer.Option("require_for_writes", "--approval", help="auto|require_for_writes|require_all"),
    max_steps: int = typer.Option(20, "--max-steps"),
    tools: Optional[str] = typer.Option(None, "--tools", help="Comma-separated allowed tools."),
):
    """Run an agent goal against a workspace."""
    _ensure_backend()
    base = _api()
    ws = str(Path(workspace).expanduser().resolve()) if workspace else str(Path.cwd().resolve())
    allowed = [t.strip() for t in tools.split(",")] if tools else None
    payload = {
        "goal": goal,
        "provider": provider,
        "model": model,
        "workspace": ws,
        "approval_mode": approval_mode,
        "max_steps": max_steps,
        "allowed_tools": allowed,
    }
    console.print(
        Panel.fit(
            f"[bold]Agent run[/bold]\nGoal: {goal}\nWorkspace: {ws}\nApproval: {approval_mode}",
            border_style="cyan",
        )
    )
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{base}/v1/agents/runs", json=payload)
        r.raise_for_status()
        data = r.json()
        run_id = data["id"]
    asyncio.run(_stream_agent(base, run_id))


@app.command()
def models():
    """List available models across enabled providers."""
    _ensure_backend()
    with httpx.Client(timeout=10.0) as client:
        ms = client.get(f"{_api()}/v1/models").json()
    if not ms:
        console.print("[yellow]No models available. Pull one with: faux-code pull <model>[/yellow]")
        return
    by_provider: dict[str, list[str]] = {}
    for m in ms:
        by_provider.setdefault(m["provider_name"], []).append(m["id"])
    for prov, lst in by_provider.items():
        console.print(f"[bold]{prov}[/bold]")
        for m in lst:
            console.print(f"  {m}")


@app.command()
def pull(model: str = typer.Argument(...)):
    """Pull an Ollama model."""
    if not _which("ollama"):
        console.print("[red]Ollama not installed. Run ./infra/scripts/install_ollama.sh[/red]")
        raise typer.Exit(1)
    subprocess.run(["ollama", "pull", model], check=False)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8765):
    """Start the backend server (foreground)."""
    os.environ["FAUX_HOST"] = host
    os.environ["FAUX_PORT"] = str(port)
    from backend.app.main import run as _run

    _run()


def _which(name: str) -> Optional[str]:
    from shutil import which

    return which(name)


def main():
    app()


if __name__ == "__main__":
    main()
