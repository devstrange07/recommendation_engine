"""Shared LLM clients (OpenAI + DeepSeek) with optional LangSmith wrapping."""

from __future__ import annotations

import json
import os
import random
import time
from typing import Any, Callable, TypeVar

import openai
from openai import OpenAI
from pydantic import BaseModel

from app.config import get_settings, langsmith_key_present

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"

_embedding_client: OpenAI | None = None
_chat_client: OpenAI | None = None
_langsmith_configured = False

T = TypeVar("T")


def retry_on_rate_limit(fn: Callable[[], T]) -> T:
    """Retry on 429 / connection / timeout with exponential backoff + jitter."""
    settings = get_settings()
    delay = settings.normalize_retry_base_delay_seconds
    last_exc: Exception | None = None
    for attempt in range(settings.normalize_max_retries + 1):
        try:
            return fn()
        except (
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APITimeoutError,
        ) as exc:
            last_exc = exc
            if attempt == settings.normalize_max_retries:
                raise
            time.sleep(delay + random.uniform(0, delay * 0.5))
            delay *= 2
    assert last_exc is not None
    raise last_exc


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


def _maybe_wrap(client: OpenAI) -> OpenAI:
    if not configure_langsmith():
        return client
    try:
        from langsmith.wrappers import wrap_openai

        return wrap_openai(client)
    except Exception as e:
        print(f"WARN: LangSmith wrap_openai failed: {e}")
        return client


def chat_provider() -> str:
    p = (get_settings().chat_provider or "openai").strip().lower()
    return p if p in ("openai", "deepseek") else "openai"


def is_deepseek() -> bool:
    return chat_provider() == "deepseek"


def openai_key_present(settings=None) -> bool:
    s = settings or get_settings()
    key = (s.openai_api_key or "").strip()
    return bool(key) and key != "sk-your-key-here"


def deepseek_key_present(settings=None) -> bool:
    s = settings or get_settings()
    return bool((s.deepseek_api_key or "").strip())


def chat_key_present(settings=None) -> bool:
    """True if the active chat provider has a usable API key."""
    s = settings or get_settings()
    if chat_provider() == "deepseek":
        return deepseek_key_present(s)
    return openai_key_present(s)


def get_embedding_client() -> OpenAI:
    """Always OpenAI — used for embeddings only."""
    global _embedding_client
    if _embedding_client is None:
        settings = get_settings()
        client = OpenAI(api_key=settings.openai_api_key or "missing")
        _embedding_client = _maybe_wrap(client)
    return _embedding_client


def get_chat_client() -> OpenAI:
    """OpenAI or DeepSeek client for chat / pipeline / vision."""
    global _chat_client
    if _chat_client is None:
        settings = get_settings()
        if chat_provider() == "deepseek":
            client = OpenAI(
                api_key=settings.deepseek_api_key or "missing",
                base_url=DEEPSEEK_BASE_URL,
            )
        else:
            client = OpenAI(api_key=settings.openai_api_key or "missing")
        _chat_client = _maybe_wrap(client)
    return _chat_client


def get_openai() -> OpenAI:
    """Backward-compatible alias: embedding client (historical OpenAI-only usage)."""
    return get_embedding_client()


def chat_model() -> str:
    settings = get_settings()
    model = (settings.chat_model or "").strip()
    if chat_provider() == "deepseek":
        if not model or model.startswith("gpt-"):
            return DEFAULT_DEEPSEEK_MODEL
        return model
    return model or "gpt-5.4-mini"


def embedding_model() -> str:
    return get_settings().embedding_model


def chat_completion_kwargs(*, for_tools: bool = False) -> dict:
    """Kwargs for /v1/chat/completions (normalize / ingest / vision / DeepSeek chat)."""
    effort = get_settings().chat_reasoning_effort.strip()
    if chat_provider() == "deepseek":
        if for_tools or not effort or effort.lower() == "none":
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        # DeepSeek thinking: effort is high|max when enabled
        ds_effort = "max" if effort.lower() in ("max", "xhigh") else "high"
        return {
            "reasoning_effort": ds_effort,
            "extra_body": {"thinking": {"type": "enabled"}},
        }
    if not effort or effort.lower() == "none":
        return {}
    return {"reasoning_effort": effort}


def responses_kwargs() -> dict:
    """Kwargs for /v1/responses (OpenAI chat agent only)."""
    if chat_provider() == "deepseek":
        return {}
    effort = get_settings().chat_reasoning_effort.strip()
    if not effort or effort.lower() == "none":
        return {}
    return {"reasoning": {"effort": effort, "summary": "auto"}}


def _tool_parameters_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    # Chat Completions tools expect a plain object schema; keep $defs for $ref resolution.
    if schema.get("type") != "object":
        schema = {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
        }
    schema.pop("title", None)
    return schema


def build_submit_tool(
    *,
    name: str,
    description: str,
    parameters_model: type[BaseModel],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": _tool_parameters_schema(parameters_model),
        },
    }


def parse_forced_tool_args(
    message: Any,
    *,
    tool_name: str,
    validate: Callable[[dict], T],
) -> T:
    tool_calls = getattr(message, "tool_calls", None) or []
    for tc in tool_calls:
        fn = getattr(tc, "function", None)
        if fn is None:
            continue
        if getattr(fn, "name", None) != tool_name:
            continue
        raw = getattr(fn, "arguments", None) or "{}"
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(data, dict):
            raise ValueError(f"tool args must be object, got {type(data)}")
        return validate(data)
    raise ValueError(f"expected tool call '{tool_name}', got none")


def call_with_forced_tool(
    *,
    messages: list[dict[str, Any]],
    tool_name: str,
    tool_description: str,
    parameters_model: type[BaseModel],
    validate: Callable[[dict], T],
) -> T:
    """Force a tool call for structured output (DeepSeek-safe with thinking). Retries once."""
    client = get_chat_client()
    model = chat_model()
    tools = [
        build_submit_tool(
            name=tool_name,
            description=tool_description,
            parameters_model=parameters_model,
        )
    ]
    def _once(
        msgs: list[dict[str, Any]],
        *,
        tool_choice: str | dict[str, Any],
        kwargs: dict[str, Any],
    ) -> T:
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        )
        message = resp.choices[0].message
        return parse_forced_tool_args(message, tool_name=tool_name, validate=validate)

    try:
        # Phase 1: preserve thinking and strongly prompt tool usage.
        return _once(
            messages,
            tool_choice="auto",
            kwargs=chat_completion_kwargs(for_tools=False),
        )
    except Exception:
        repair = list(messages) + [
            {
                "role": "user",
                "content": (
                    f"Your previous reply was invalid. You MUST call the `{tool_name}` tool "
                    "with arguments that exactly match the tool schema. "
                    "Do not put JSON in the message content — only the tool call."
                ),
            }
        ]
        # Phase 2: guarantee a tool call by forcing it with thinking disabled.
        return _once(
            repair,
            tool_choice={"type": "function", "function": {"name": tool_name}},
            kwargs=chat_completion_kwargs(for_tools=True),
        )
