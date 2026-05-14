"""HuggingFace Inference Router — OpenAI-compatible endpoint at router.huggingface.co."""

from __future__ import annotations

from ..settings import get_settings
from .openai_compat import OpenAICompatProvider


class HuggingFaceProvider(OpenAICompatProvider):
    """HuggingFace Inference router.

    Reference: https://huggingface.co/docs/inference-providers/index
    """

    def __init__(self) -> None:
        s = get_settings()
        super().__init__(
            provider_id="huggingface",
            name="HuggingFace Inference",
            base_url="https://router.huggingface.co/v1",
            api_key=s.hf_token,
            requires_key=True,
            default_models=[
                "meta-llama/Llama-3.3-70B-Instruct",
                "Qwen/Qwen2.5-Coder-32B-Instruct",
                "deepseek-ai/DeepSeek-V3",
            ],
            description="HuggingFace inference router — proxies many providers.",
        )
