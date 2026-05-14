"""Run the canonical agent eval task suite.

Usage:
    python -m tests.evals.run_evals --model llama3.2:3b
    python -m tests.evals.run_evals --provider groq --model llama-3.3-70b-versatile

Each task gets its own tmpdir workspace. The script runs the agent loop in
process (no HTTP), then validates against expected text or expected file
contents. Exit code 0 if all tasks pass.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

# Ensure repo root on path when run via "python tests/evals/run_evals.py".
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.agent import AgentLoop, AgentEventKind  # noqa: E402


async def run_task(task: dict[str, Any], *, provider: str | None, model: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="faux-eval-") as td:
        workspace = Path(td)
        for name, content in (task.get("setup_files") or {}).items():
            p = workspace / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

        loop = AgentLoop(
            provider=provider,
            model=model,
            goal=task["goal"],
            workspace=str(workspace),
            approval_mode="auto",
            allowed_tools=task.get("allowed_tools"),
            max_steps=int(task.get("max_steps", 15)),
        )

        final_text = ""
        tool_calls = Counter()
        steps = 0
        error: str | None = None
        try:
            async for ev in loop.run():
                if ev.kind == AgentEventKind.TOOL_CALL:
                    tool_calls[ev.payload.get("name", "")] += 1
                elif ev.kind == AgentEventKind.ASSISTANT_MESSAGE:
                    text = ev.payload.get("content", "")
                    if text:
                        final_text = text
                elif ev.kind == AgentEventKind.FINISHED:
                    steps = ev.payload.get("steps_taken", 0)
                    if ev.payload.get("final"):
                        final_text = ev.payload["final"]
                elif ev.kind == AgentEventKind.ERROR:
                    error = ev.payload.get("message", "unknown error")
        except Exception as e:
            error = str(e)

        passed, reason = _validate(task, final_text, workspace)
        return {
            "id": task["id"],
            "passed": passed and error is None,
            "reason": reason if error is None else f"error: {error}",
            "final_text": final_text[:500],
            "tool_calls": dict(tool_calls),
            "steps": steps,
        }


def _validate(task: dict[str, Any], final_text: str, workspace: Path) -> tuple[bool, str]:
    needs = task.get("expect_text_includes") or []
    for s in needs:
        if s.lower() not in final_text.lower():
            return False, f"final missing substring: {s!r}"
    any_needs = task.get("expect_text_includes_any") or []
    if any_needs:
        if not any(s.lower() in final_text.lower() for s in any_needs):
            return False, f"final missing any of: {any_needs!r}"
    for relpath, needles in (task.get("expect_files") or {}).items():
        p = workspace / relpath
        if not p.exists():
            return False, f"expected file not created: {relpath}"
        text = p.read_text(encoding="utf-8", errors="replace")
        for n in needles:
            if n not in text:
                return False, f"{relpath} missing: {n!r}"
    return True, "ok"


async def main_async(args) -> int:
    tasks_path = Path(args.tasks)
    suite = yaml.safe_load(tasks_path.read_text())
    tasks = suite["tasks"]
    if args.only:
        wanted = set(args.only)
        tasks = [t for t in tasks if t["id"] in wanted]
    print(f"Running {len(tasks)} eval task(s) with provider={args.provider or 'auto'} model={args.model}")
    print("=" * 70)
    results = []
    for t in tasks:
        print(f"\n→ {t['id']}: {t['description']}")
        res = await run_task(t, provider=args.provider, model=args.model)
        mark = "✓" if res["passed"] else "✗"
        print(f"  {mark} {res['reason']}  (steps={res['steps']}, tools={res['tool_calls']})")
        if not res["passed"]:
            print(f"    final: {res['final_text'][:200]}")
        results.append(res)
    print("\n" + "=" * 70)
    npass = sum(1 for r in results if r["passed"])
    print(f"PASSED {npass}/{len(results)}")
    return 0 if npass == len(results) else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", default=str(Path(__file__).with_name("tasks.yaml")))
    p.add_argument("--provider", default=None)
    p.add_argument("--model", default="llama3.2:3b")
    p.add_argument("--only", action="append", help="Run only specific task id(s).")
    args = p.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
