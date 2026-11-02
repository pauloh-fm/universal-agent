"""Runtime configuration, loaded from environment variables or a `.env` file.

Every setting has a safe default so the project runs offline (``LLM_PROVIDER=fake``)
right after cloning. See ``docs/configuration.md`` for the full reference.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Model provider -------------------------------------------------------------
    llm_provider: Literal["fake", "openai"] = "fake"
    """`fake` = deterministic offline model (tests, demos). `openai` = any OpenAI-compatible API."""

    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    """Leave empty for api.openai.com. Point to any OpenAI-compatible server
    (Ollama, vLLM, LiteLLM, OpenRouter, a gateway in front of Anthropic/Gemini...)."""

    llm_api_key: SecretStr | None = None
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_timeout_seconds: float = Field(default=60, gt=0, le=600)

    # --- Agent runtime --------------------------------------------------------------
    agents_dir: Path = Path("agents")
    data_dir: Path = Path(".data")
    max_steps: int = Field(default=8, ge=1, le=50)
    """Maximum model calls per user turn. Protects against tool-call loops."""

    max_context_messages: int = Field(default=40, ge=4, le=500)
    require_confirmation_for: list[Literal["read", "write"]] = ["write"]
    """Tool risk levels that pause the graph and wait for human approval."""

    # --- HTTP API -------------------------------------------------------------------
    api_token: SecretStr | None = None
    """If set, every request except /health must send `Authorization: Bearer <token>`."""

    log_level: str = "INFO"

    @model_validator(mode="after")
    def _check_provider(self) -> Settings:
        if self.llm_provider == "openai" and not self.llm_api_key and not self.llm_base_url:
            raise ValueError("LLM_PROVIDER=openai needs LLM_API_KEY (or LLM_BASE_URL for a local server)")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
