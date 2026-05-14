"""Application settings loaded from environment variables with sensible defaults."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    host: str = Field("127.0.0.1", alias="FAUX_HOST")
    port: int = Field(8765, alias="FAUX_PORT")
    data_dir: Path = Field(Path("backend/data"), alias="FAUX_DATA_DIR")
    workspace_root: Path = Field(Path("workspaces"), alias="FAUX_WORKSPACE_ROOT")
    log_level: str = Field("INFO", alias="FAUX_LOG_LEVEL")
    cors_origins: str = Field(
        "http://localhost:3000,http://127.0.0.1:3000",
        alias="FAUX_CORS_ORIGINS",
    )

    ollama_base_url: str = Field("http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    ollama_default_chat: str = Field(
        "llama3.1:8b-instruct-q4_K_M", alias="OLLAMA_DEFAULT_CHAT"
    )
    ollama_default_code: str = Field(
        "qwen2.5-coder:7b-instruct-q4_K_M", alias="OLLAMA_DEFAULT_CODE"
    )
    ollama_default_embed: str = Field("nomic-embed-text", alias="OLLAMA_DEFAULT_EMBED")

    groq_api_key: str = Field("", alias="GROQ_API_KEY")
    openrouter_api_key: str = Field("", alias="OPENROUTER_API_KEY")
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")
    cerebras_api_key: str = Field("", alias="CEREBRAS_API_KEY")
    hf_token: str = Field("", alias="HF_TOKEN")

    vllm_base_url: str = Field("", alias="VLLM_BASE_URL")
    vllm_api_key: str = Field("", alias="VLLM_API_KEY")

    tavily_api_key: str = Field("", alias="TAVILY_API_KEY")
    searxng_base_url: str = Field("", alias="SEARXNG_BASE_URL")

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
