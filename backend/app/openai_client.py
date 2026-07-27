"""Shared OpenAI client with optional LangSmith wrapping."""

from __future__ import annotations

import os

from openai import OpenAI

from app.config import get_settings, langsmith_key_present

_client: OpenAI | None = None
_langsmith_configured = False


def configure_langsmith() -> bool:
    """Export LangSmith env vars when API key is present. Returns True if tracing enabled."""
    global _langsmith_configured
    settings = get_settings()
    if not langsmith_key_present(settings):
        return False
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.strip()
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_tracing:
        os.environ["LANGSMITH_TRACING"] = "true"
        # legacy alias still read by some SDK paths
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key.strip())
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
    _langsmith_configured = True
    return True


def get_openai() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        client = OpenAI(api_key=settings.openai_api_key or "missing")
        if configure_langsmith():
            try:
                from langsmith.wrappers import wrap_openai

                client = wrap_openai(client)
            except Exception as e:
                print(f"WARN: LangSmith wrap_openai failed: {e}")
        _client = client
    return _client


def chat_model() -> str:
    return get_settings().chat_model


def embedding_model() -> str:
    return get_settings().embedding_model


def chat_completion_kwargs(*, for_tools: bool = False) -> dict:
    """Kwargs for /v1/chat/completions (normalize / ingest / vision)."""
    del for_tools  # unused; kept for call-site compatibility
    effort = get_settings().chat_reasoning_effort.strip()
    if not effort or effort.lower() == "none":
        return {}
    return {"reasoning_effort": effort}


def responses_kwargs() -> dict:
    """Kwargs for /v1/responses (chat agent: tools + reasoning together)."""
    effort = get_settings().chat_reasoning_effort.strip()
    if not effort or effort.lower() == "none":
        return {}
    return {"reasoning": {"effort": effort}}
