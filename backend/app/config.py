"""Centralised configuration.

All tunables live here and are overridable via environment variables or a
.env file. LLM_PROVIDER defaults to "auto": set a key or a local base URL and
the right provider is picked without flipping switches between environments.
"""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_OPENAI_BASE = "http://localhost:11434/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Research Copilot"
    environment: str = "development"

    # Persistence
    database_url: str = "sqlite:///./copilot.db"

    # LLM: auto (default) picks from keys/URL | mock | anthropic | openai
    llm_provider: str = "auto"
    llm_model: str = ""
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = ""

    # Search provider: "mock" (offline) | future: tavily, serpapi, ...
    search_provider: str = "mock"

    # Workflow tuning
    quality_threshold: float = 0.7
    max_research_passes: int = 2

    # Ops
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @staticmethod
    def _is_local_url(url: str) -> bool:
        if not url:
            return False
        host = (urlparse(url).hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "0.0.0.0"}

    def _infer_openai_base_url(self) -> str:
        if self.openai_base_url:
            return self.openai_base_url.rstrip("/")
        key = self.openai_api_key or ""
        if key.startswith("sk-or-"):
            return "https://openrouter.ai/api/v1"
        if key.startswith("gsk_"):
            return "https://api.groq.com/openai/v1"
        if key.startswith("sk-"):
            return "https://api.openai.com/v1"
        return _LOCAL_OPENAI_BASE

    @property
    def resolved_openai_base_url(self) -> str:
        return self._infer_openai_base_url()

    @property
    def resolved_openai_api_key(self) -> str:
        if self.openai_api_key:
            return self.openai_api_key
        if self._is_local_url(self.resolved_openai_base_url):
            return "ollama"
        return ""

    @property
    def resolved_llm_provider(self) -> str:
        choice = self.llm_provider.strip().lower()
        if choice in {"mock", "anthropic", "openai"}:
            return choice
        if self.anthropic_api_key:
            return "anthropic"
        if self.openai_api_key or self._is_local_url(self.openai_base_url):
            return "openai"
        return "mock"

    @property
    def resolved_llm_model(self) -> str:
        if self.llm_model:
            return self.llm_model
        provider = self.resolved_llm_provider
        if provider == "anthropic":
            return "claude-sonnet-4-6"
        if provider == "openai":
            base = self.resolved_openai_base_url
            if "openrouter" in base:
                return "meta-llama/llama-3.3-70b-instruct:free"
            if "groq" in base:
                return "llama-3.3-70b-versatile"
            if self._is_local_url(base):
                return "llama3.2"
            return "gpt-4o-mini"
        return "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
