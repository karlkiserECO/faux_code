"""Cerebras provider — fast Llama inference on Cerebras CS-3 (free tier)."""

from __future__ import annotations

from ..settings import get_settings
from .openai_compat import OpenAICompatProvider


class CerebrasProvider(OpenAICompatProvider):
    def __init__(self) -> None:
        s = get_settings()
        super().__init__(
            provider_id="cerebras",
            name="Cerebras (free tier, very fast)",
            base_url="https://api.cerebras.ai/v1",
            api_key=s.cerebras_api_key,
            requires_key=True,
            default_models=[
                "llama-3.3-70b",
                "llama3.1-8b",
                "qwen-3-32b",
            ],
            description="Cerebras CS-3 inference — typically 1000+ tok/s.",
        )
