"""Config resolution: provider auto-selection and CORS parsing."""
from __future__ import annotations

from app.config import Settings


def test_search_provider_auto_resolution():
    assert Settings(_env_file=None, search_provider="auto", tavily_api_key=None).resolved_search_provider == "mock"
    assert Settings(_env_file=None, search_provider="auto", tavily_api_key="tvly-x").resolved_search_provider == "tavily"
    assert Settings(_env_file=None, search_provider="mock", tavily_api_key="tvly-x").resolved_search_provider == "mock"


def test_llm_provider_and_model_from_key_prefix():
    groq = Settings(_env_file=None, openai_api_key="gsk_abc")
    assert groq.resolved_llm_provider == "openai"
    assert "groq" in groq.resolved_openai_base_url
    assert groq.resolved_llm_model == "llama-3.3-70b-versatile"

    anthropic = Settings(_env_file=None, anthropic_api_key="sk-ant-x")
    assert anthropic.resolved_llm_provider == "anthropic"

    none = Settings(_env_file=None)
    assert none.resolved_llm_provider == "mock"


def test_cors_origins_accepts_comma_separated():
    s = Settings(_env_file=None, cors_origins="https://a.vercel.app, http://localhost:5173")
    assert s.cors_origins == ["https://a.vercel.app", "http://localhost:5173"]
