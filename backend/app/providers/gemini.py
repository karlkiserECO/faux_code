"""Google Gemini provider with OpenAI-compatible endpoint at generativelanguage.googleapis.com."""

from __future__ import annotations

from ..settings import get_settings
from .openai_compat import OpenAICompatProvider


class GeminiProvider(OpenAICompatProvider):
    """Use Google's OpenAI-compatible Gemini endpoint.

    Reference: https://ai.google.dev/gemini-api/docs/openai
    """

    def __init__(self) -> None:
        s = get_settings()
        super().__init__(
            provider_id="gemini",
            name="Google Gemini (free tier)",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=s.gemini_api_key,
            requires_key=True,
            default_models=[
                "gemini-2.0-flash",
                "gemini-2.0-flash-thinking-exp",
                "gemini-1.5-flash",
                "gemini-1.5-pro",
            ],
            description="Google Gemini via OpenAI-compatible endpoint. Free tier: ~60 RPM.",
        )
