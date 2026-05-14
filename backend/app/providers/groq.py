"""Groq provider — fast Llama/Mixtral inference, generous free tier."""

from __future__ import annotations

from ..settings import get_settings
from .openai_compat import OpenAICompatProvider


class GroqProvider(OpenAICompatProvider):
    def __init__(self) -> None:
        s = get_settings()
        super().__init__(
            provider_id="groq",
            name="Groq (free, very fast)",
            base_url="https://api.groq.com/openai/v1",
            api_key=s.groq_api_key,
            requires_key=True,
            default_models=[
                "llama-3.3-70b-versatile",
                "llama-3.1-8b-instant",
                "qwen-2.5-coder-32b",
                "deepseek-r1-distill-llama-70b",
            ],
            description="Groq LPU inference — extremely fast (300+ tok/s).",
        )
