"""Runtime settings (API keys, preferences) — stored in DB and reloaded."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import ApiKey, get_session
from ..providers.registry import reload_providers

router = APIRouter(prefix="/v1/settings", tags=["settings"])

KNOWN_KEYS = [
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
    "CEREBRAS_API_KEY",
    "HF_TOKEN",
    "TAVILY_API_KEY",
    "VLLM_BASE_URL",
    "VLLM_API_KEY",
    "OLLAMA_BASE_URL",
]


class KeyUpdate(BaseModel):
    keys: dict[str, str]


@router.get("/keys")
def get_keys(session: Session = Depends(get_session)):
    rows = session.exec(select(ApiKey)).all()
    by_provider = {r.provider: r for r in rows}
    out = {}
    for k in KNOWN_KEYS:
        row = by_provider.get(k)
        out[k] = {
            "set": bool(row and row.value) or bool(os.getenv(k)),
            "preview": _preview(row.value if row else os.getenv(k, "")),
        }
    return out


@router.post("/keys")
def update_keys(body: KeyUpdate, session: Session = Depends(get_session)):
    rows = {r.provider: r for r in session.exec(select(ApiKey)).all()}
    for k, v in body.keys.items():
        if k not in KNOWN_KEYS:
            continue
        if k in rows:
            rows[k].value = v
            rows[k].updated_at = datetime.now(timezone.utc)
            session.add(rows[k])
        else:
            session.add(ApiKey(provider=k, value=v))
        # Also push into the live env so settings.get_settings() picks it up after reload.
        os.environ[k] = v
    session.commit()
    # Force the settings + provider registry to refresh from env.
    from ..settings import get_settings
    get_settings.__globals__["_settings"] = None  # type: ignore[attr-defined]
    reload_providers()
    return {"ok": True}


def _preview(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return "***"
    return f"{v[:4]}…{v[-3:]}"


def load_keys_into_env() -> None:
    """Called at startup — push DB-stored keys into process env."""
    from ..db.session import _get_engine
    from sqlmodel import Session

    try:
        with Session(_get_engine()) as s:
            for r in s.exec(select(ApiKey)).all():
                if r.value:
                    os.environ.setdefault(r.provider, r.value)
    except Exception:
        pass
