"""Self-hosted vLLM provider (optional)."""

from __future__ import annotations

from ..settings import get_settings
from .openai_compat import OpenAICompatProvider


class VLLMProvider(OpenAICompatProvider):
    def __init__(self) -> None:
        s = get_settings()
        base = s.vllm_base_url.rstrip("/")
        super().__init__(
            provider_id="vllm",
            name="Self-hosted vLLM",
            base_url=f"{base}/v1" if base and not base.endswith("/v1") else base,
            api_key=s.vllm_api_key,
            requires_key=False,
            default_models=[],
            description="Self-hosted vLLM server (e.g. on a rented cloud GPU).",
        )
