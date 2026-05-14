"""OpenRouter provider — meta-router across many models including free tiers."""

from __future__ import annotations

from ..settings import get_settings
from .openai_compat import OpenAICompatProvider


class OpenRouterProvider(OpenAICompatProvider):
    def __init__(self) -> None:
        s = get_settings()
        super().__init__(
            provider_id="openrouter",
            name="OpenRouter (many free models)",
            base_url="https://openrouter.ai/api/v1",
            api_key=s.openrouter_api_key,
            requires_key=True,
            default_models=[
                "deepseek/deepseek-chat-v3.1:free",
                "deepseek/deepseek-r1:free",
                "qwen/qwen-2.5-coder-32b-instruct:free",
                "meta-llama/llama-3.3-70b-instruct:free",
                "google/gemini-2.0-flash-exp:free",
                "mistralai/mistral-small-3.1-24b-instruct:free",
            ],
            description="OpenRouter — many models with :free tier endpoints.",
            extra_headers={
                "HTTP-Referer": "https://github.com/karl-kiser/faux_code",
                "X-Title": "faux_code",
            },
        )
