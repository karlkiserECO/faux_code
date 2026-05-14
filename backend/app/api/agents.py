"""Agent runs API.

POST /v1/agents/runs        -> create a run, returns id
GET  /v1/agents/runs        -> list recent runs
GET  /v1/agents/runs/{id}   -> run metadata + events
GET  /v1/agents/runs/{id}/events -> SSE stream of events (live)
POST /v1/agents/runs/{id}/approve -> resolve a pending approval
POST /v1/agents/runs/{id}/cancel  -> stop the run

A run is associated with an asyncio task; events go through a per-run queue.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..agent import AgentEventKind, AgentLoop
from ..db import AgentEvent as DBEvent
from ..db import AgentRun, get_session
from ..db.session import _get_engine
from ..providers import ChatMessage
from ..streaming import event_stream

router = APIRouter(prefix="/v1/agents", tags=["agents"])


class RunRequest(BaseModel):
    goal: str
    provider: Optional[str] = None
    model: str
    workspace: Optional[str] = None
    approval_mode: str = "auto"
    allowed_tools: Optional[list[str]] = None
    max_steps: int = 25
    system_prompt: Optional[str] = None
    history: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    approve: bool


_RUNS: dict[str, "RunHandle"] = {}


class RunHandle:
    """Bookkeeping for a single in-memory run."""

    def __init__(self, run: AgentRun):
        self.run = run
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.finished = asyncio.Event()
        self.cancel = asyncio.Event()
        self.pending_approval: Optional[asyncio.Future[bool]] = None
        self.pending_approval_payload: Optional[dict[str, Any]] = None
        self.task: Optional[asyncio.Task[None]] = None
        self.lock = asyncio.Lock()

    def emit(self, ev: dict[str, Any]) -> None:
        try:
            self.events.put_nowait(ev)
        except Exception:
            pass


def _persist_event(run_id: str, kind: str, payload: dict[str, Any]) -> None:
    from sqlmodel import Session as _S

    with _S(_get_engine()) as s:
        s.add(DBEvent(run_id=run_id, kind=kind, payload_json=json.dumps(payload, default=str)))
        s.commit()


def _update_run(run_id: str, **fields: Any) -> None:
    from sqlmodel import Session as _S

    with _S(_get_engine()) as s:
        r = s.get(AgentRun, run_id)
        if not r:
            return
        for k, v in fields.items():
            setattr(r, k, v)
        r.updated_at = datetime.now(timezone.utc)
        s.add(r)
        s.commit()


async def _approval_callback(run_id: str, op: str, args: dict[str, Any]) -> bool:
    """Called from the agent loop when a write tool needs approval."""
    handle = _RUNS.get(run_id)
    if not handle:
        return True
    fut: asyncio.Future[bool] = asyncio.get_event_loop().create_future()
    handle.pending_approval = fut
    handle.pending_approval_payload = {"op": op, "args": args}
    payload = {"op": op, "args": args}
    _persist_event(run_id, AgentEventKind.APPROVAL_REQUEST.value, payload)
    handle.emit({"event": AgentEventKind.APPROVAL_REQUEST.value, "data": payload})
    _update_run(run_id, status="awaiting_approval")
    try:
        decided = await fut
    except asyncio.CancelledError:
        return False
    finally:
        handle.pending_approval = None
        handle.pending_approval_payload = None
    _persist_event(
        run_id,
        AgentEventKind.APPROVAL_RESOLVED.value,
        {"op": op, "approved": decided},
    )
    handle.emit(
        {
            "event": AgentEventKind.APPROVAL_RESOLVED.value,
            "data": {"op": op, "approved": decided},
        }
    )
    _update_run(run_id, status="running")
    return decided


async def _drive_run(handle: RunHandle, payload: RunRequest) -> None:
    run_id = handle.run.id
    try:
        history_messages: list[ChatMessage] = []
        for m in payload.history or []:
            history_messages.append(
                ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
            )

        async def approval_cb(op: str, args: dict[str, Any]) -> bool:
            return await _approval_callback(run_id, op, args)

        loop = AgentLoop(
            provider=payload.provider,
            model=payload.model,
            goal=payload.goal,
            history=history_messages,
            workspace=payload.workspace,
            approval_mode=payload.approval_mode,
            allowed_tools=payload.allowed_tools,
            max_steps=payload.max_steps,
            system_prompt=payload.system_prompt,
            request_approval=approval_cb,
        )
        _update_run(run_id, status="running")
        steps = 0
        async for ev in loop.run():
            if handle.cancel.is_set():
                handle.emit(
                    {"event": "error", "data": {"message": "cancelled"}}
                )
                _persist_event(run_id, "error", {"message": "cancelled"})
                _update_run(run_id, status="cancelled")
                return
            sse = ev.to_sse()
            handle.emit(sse)
            _persist_event(run_id, sse["event"], sse["data"])
            if ev.kind == AgentEventKind.ASSISTANT_MESSAGE:
                steps = sse["data"].get("step", steps) + 1
                _update_run(run_id, steps_taken=steps)
            if ev.kind == AgentEventKind.FINISHED:
                status = sse["data"].get("status", "completed")
                _update_run(run_id, status=status, steps_taken=sse["data"].get("steps_taken", steps))
                return
            if ev.kind == AgentEventKind.ERROR:
                _update_run(run_id, status="failed", error=sse["data"].get("message", ""))
                return
        # If the loop exits without explicit finish:
        _update_run(run_id, status="completed", steps_taken=steps)
    except Exception as e:
        handle.emit({"event": "error", "data": {"message": str(e)}})
        _persist_event(run_id, "error", {"message": str(e)})
        _update_run(run_id, status="failed", error=str(e))
    finally:
        handle.finished.set()


@router.post("/runs")
async def create_run(body: RunRequest, session: Session = Depends(get_session)):
    run = AgentRun(
        goal=body.goal,
        provider=body.provider or "ollama",
        model=body.model,
        workspace_path=body.workspace,
        approval_mode=body.approval_mode,
        max_steps=body.max_steps,
        status="pending",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    handle = RunHandle(run)
    _RUNS[run.id] = handle
    handle.task = asyncio.create_task(_drive_run(handle, body))
    return {
        "id": run.id,
        "status": run.status,
        "events_url": f"/v1/agents/runs/{run.id}/events",
    }


@router.get("/runs")
def list_runs(session: Session = Depends(get_session)):
    rows = session.exec(
        select(AgentRun).order_by(AgentRun.created_at.desc()).limit(50)
    ).all()
    return [
        {
            "id": r.id,
            "goal": r.goal[:120],
            "status": r.status,
            "model": r.model,
            "provider": r.provider,
            "steps_taken": r.steps_taken,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)):
    r = session.get(AgentRun, run_id)
    if not r:
        raise HTTPException(404, "Not found")
    events = session.exec(
        select(DBEvent).where(DBEvent.run_id == run_id).order_by(DBEvent.created_at)
    ).all()
    return {
        "id": r.id,
        "goal": r.goal,
        "status": r.status,
        "model": r.model,
        "provider": r.provider,
        "approval_mode": r.approval_mode,
        "steps_taken": r.steps_taken,
        "max_steps": r.max_steps,
        "workspace_path": r.workspace_path,
        "error": r.error,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
        "events": [
            {
                "kind": e.kind,
                "payload": json.loads(e.payload_json) if e.payload_json else {},
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }


@router.get("/runs/{run_id}/events")
async def stream_run_events(run_id: str):
    handle = _RUNS.get(run_id)
    if not handle:
        # Still allow replay from DB if the run is over.
        from sqlmodel import Session as _S

        with _S(_get_engine()) as s:
            r = s.get(AgentRun, run_id)
            if not r:
                raise HTTPException(404, "Not found")
            events = s.exec(
                select(DBEvent).where(DBEvent.run_id == run_id).order_by(DBEvent.created_at)
            ).all()

        async def replay():
            for e in events:
                yield {
                    "event": e.kind,
                    "data": json.loads(e.payload_json) if e.payload_json else {},
                }

        return StreamingResponse(event_stream(replay()), media_type="text/event-stream")

    async def live():
        while True:
            if handle.finished.is_set() and handle.events.empty():
                break
            try:
                ev = await asyncio.wait_for(handle.events.get(), timeout=1.0)
                yield ev
            except asyncio.TimeoutError:
                if handle.finished.is_set() and handle.events.empty():
                    break
                continue

    return StreamingResponse(event_stream(live()), media_type="text/event-stream")


@router.post("/runs/{run_id}/approve")
async def approve(run_id: str, body: ApprovalDecision):
    handle = _RUNS.get(run_id)
    if not handle or not handle.pending_approval:
        raise HTTPException(400, "No pending approval for this run.")
    handle.pending_approval.set_result(body.approve)
    return {"ok": True}


@router.post("/runs/{run_id}/cancel")
async def cancel(run_id: str):
    handle = _RUNS.get(run_id)
    if not handle:
        raise HTTPException(404, "Not running")
    handle.cancel.set()
    if handle.pending_approval and not handle.pending_approval.done():
        handle.pending_approval.set_result(False)
    if handle.task:
        handle.task.cancel()
    _update_run(run_id, status="cancelled")
    return {"ok": True}


@router.get("/tools")
def list_available_tools():
    from ..tools import list_tools

    return [
        {
            "name": t.name,
            "description": t.description,
            "writes": t.writes,
            "parameters": t.parameters,
        }
        for t in list_tools()
    ]
