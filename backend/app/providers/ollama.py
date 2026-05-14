"""Ollama provider — uses Ollama's OpenAI-compatible endpoint plus native API for model listing."""

from __future__ import annotations

import httpx

from ..settings import get_settings
from .openai_compat import OpenAICompatProvider


class OllamaProvider(OpenAICompatProvider):
    def __init__(self) -> None:
        s = get_settings()
        super().__init__(
            provider_id="ollama",
            name="Ollama (local)",
            base_url=f"{s.ollama_base_url}/v1",
            api_key="ollama",  # any non-empty value
            requires_key=False,
            default_models=[
                s.ollama_default_chat,
                s.ollama_default_code,
            ],
            description="Local Ollama runtime — fully offline, fully private.",
        )
        self._native_base = s.ollama_base_url.rstrip("/")

    @property
    def enabled(self) -> bool:
        return True  # always advertise; connectivity is checked at request time

    async def list_models(self) -> list[str]:
        """Use Ollama's native /api/tags endpoint, which is more reliable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._native_base}/api/tags")
                r.raise_for_status()
                data = r.json()
                return [m["name"] for m in data.get("models", []) if "name" in m]
        except Exception:
            return self.default_models

    async def is_alive(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{self._native_base}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def pull(self, model: str):
        """Stream a model pull from Ollama."""
        import json

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self._native_base}/api/pull",
                json={"model": model, "stream": True},
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """Get embeddings via Ollama's native API."""
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for t in texts:
                r = await client.post(
                    f"{self._native_base}/api/embeddings",
                    json={"model": model, "prompt": t},
                )
                r.raise_for_status()
                out.append(r.json().get("embedding", []))
        return out
