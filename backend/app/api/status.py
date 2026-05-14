"""System status + model management endpoints used by the welcome screen."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..providers import list_providers
from ..providers.ollama import OllamaProvider
from ..providers.registry import get_provider
from ..settings import get_settings
from ..streaming import event_stream

router = APIRouter(prefix="/v1/status", tags=["status"])


@router.get("/system")
async def system_status():
    s = get_settings()
    ollama: OllamaProvider = get_provider("ollama")  # type: ignore[assignment]
    alive = await ollama.is_alive()
    local_models: list[str] = []
    if alive:
        try:
            local_models = await ollama.list_models()
        except Exception:
            local_models = []
    providers = []
    for p in list_providers():
        providers.append(
            {
                "id": p.id,
                "name": p.name,
                "enabled": p.enabled,
                "requires_key": p.requires_key,
                "description": p.description,
            }
        )
    return {
        "ollama": {
            "base_url": s.ollama_base_url,
            "alive": alive,
            "models_installed": local_models,
            "default_chat": s.ollama_default_chat,
            "default_code": s.ollama_default_code,
            "default_embed": s.ollama_default_embed,
        },
        "providers": providers,
        "workspace_root": str(s.workspace_root.resolve()),
        "data_dir": str(s.data_dir.resolve()),
    }


class PullRequest(BaseModel):
    model: str


@router.post("/ollama/pull")
async def pull_model(body: PullRequest):
    """Stream an Ollama model pull as SSE."""
    ollama: OllamaProvider = get_provider("ollama")  # type: ignore[assignment]

    async def gen():
        try:
            async for ev in ollama.pull(body.model):
                yield {"event": "progress", "data": ev}
            yield {"event": "complete", "data": {"model": body.model}}
        except Exception as e:
            yield {"event": "error", "data": {"message": str(e)}}

    return StreamingResponse(event_stream(gen()), media_type="text/event-stream")


@router.get("/ollama/recommended")
def recommended_models():
    """Curated set tuned for a ~16 GB Apple Silicon machine."""
    s = get_settings()
    return [
        {
            "id": s.ollama_default_chat,
            "role": "chat",
            "description": "General chat (Llama 3.1 8B, 4-bit quantized).",
            "size_gb": 4.7,
        },
        {
            "id": s.ollama_default_code,
            "role": "code",
            "description": "Coding + agentic work (Qwen2.5-Coder 7B, 4-bit).",
            "size_gb": 4.4,
        },
        {
            "id": s.ollama_default_embed,
            "role": "embed",
            "description": "Embeddings for RAG (nomic-embed-text).",
            "size_gb": 0.27,
        },
        {
            "id": "llama3.2:3b",
            "role": "chat-fast",
            "description": "Smaller, faster chat — good when memory matters.",
            "size_gb": 2.0,
        },
        {
            "id": "qwen2.5:0.5b",
            "role": "scratch",
            "description": "Tiny model — useful for smoke tests.",
            "size_gb": 0.4,
        },
    ]
