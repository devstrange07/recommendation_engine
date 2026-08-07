"""Pipeline run timing + token/cost metrics (context-scoped)."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.config import get_settings

# Approximate USD per 1M tokens when model-specific rates are not set.
_DEFAULT_MODEL_RATES: dict[str, tuple[float, float]] = {
    # (input_usd_per_1m, output_usd_per_1m)
    "gpt-5.4-mini": (0.25, 2.00),
    "gpt-4o-mini": (0.15, 0.60),
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-chat": (0.14, 0.28),
}
_DEFAULT_EMBEDDING_RATES: dict[str, float] = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
}


@dataclass
class UsageBucket:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_tokens: int = 0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add_chat(self, model: str, prompt: int, completion: int) -> None:
        with self._lock:
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            entry = self.by_model.setdefault(
                model, {"prompt": 0, "completion": 0, "embedding": 0}
            )
            entry["prompt"] += prompt
            entry["completion"] += completion

    def add_embedding(self, model: str, tokens: int) -> None:
        with self._lock:
            self.embedding_tokens += tokens
            entry = self.by_model.setdefault(
                model, {"prompt": 0, "completion": 0, "embedding": 0}
            )
            entry["embedding"] += tokens

    def merge(self, other: UsageBucket) -> None:
        with self._lock:
            self.prompt_tokens += other.prompt_tokens
            self.completion_tokens += other.completion_tokens
            self.embedding_tokens += other.embedding_tokens
            for model, counts in other.by_model.items():
                entry = self.by_model.setdefault(
                    model, {"prompt": 0, "completion": 0, "embedding": 0}
                )
                entry["prompt"] += counts.get("prompt", 0)
                entry["completion"] += counts.get("completion", 0)
                entry["embedding"] += counts.get("embedding", 0)

    @property
    def total_tokens(self) -> int:
        with self._lock:
            return self.prompt_tokens + self.completion_tokens + self.embedding_tokens


_usage_var: ContextVar[UsageBucket | None] = ContextVar("pipeline_usage", default=None)


def current_usage() -> UsageBucket | None:
    return _usage_var.get()


def bind_usage(bucket: UsageBucket | None) -> Token[UsageBucket | None]:
    """Bind bucket in this thread (for ThreadPool workers)."""
    return _usage_var.set(bucket)


def reset_usage(token: Token[UsageBucket | None]) -> None:
    """Reset a bind_usage token; ignore wrong-Context errors from thread hops."""
    try:
        _usage_var.reset(token)
    except ValueError as exc:
        if "different Context" not in str(exc):
            raise


@contextmanager
def usage_scope() -> Iterator[UsageBucket]:
    """Bind a usage bucket; nested calls reuse the outer bucket."""
    existing = _usage_var.get()
    if existing is not None:
        yield existing
        return
    bucket = UsageBucket()
    token = _usage_var.set(bucket)
    try:
        yield bucket
    finally:
        reset_usage(token)


def _usage_attr(usage: Any, *names: str) -> int:
    for name in names:
        val = getattr(usage, name, None)
        if val is not None:
            return int(val)
    return 0


def record_chat_usage(resp: Any, *, model: str) -> None:
    bucket = current_usage()
    if bucket is None or resp is None:
        return
    usage = getattr(resp, "usage", None)
    if not usage:
        return
    prompt = _usage_attr(usage, "prompt_tokens", "input_tokens")
    completion = _usage_attr(usage, "completion_tokens", "output_tokens")
    if prompt == 0 and completion == 0:
        total = _usage_attr(usage, "total_tokens")
        prompt = total
    bucket.add_chat(model, prompt, completion)


def record_embedding_usage(resp: Any, *, model: str) -> None:
    bucket = current_usage()
    if bucket is None or resp is None:
        return
    usage = getattr(resp, "usage", None)
    if not usage:
        return
    tokens = _usage_attr(usage, "total_tokens", "prompt_tokens", "input_tokens")
    if tokens:
        bucket.add_embedding(model, tokens)


@dataclass
class PhaseTimer:
    phases: list[dict[str, Any]] = field(default_factory=list)
    _active: str | None = None
    _started: float = 0.0
    _run_started: float = field(default_factory=time.perf_counter)

    def start(self, phase: str) -> None:
        self.stop()
        self._active = phase
        self._started = time.perf_counter()

    def stop(self) -> None:
        if self._active is None:
            return
        elapsed = time.perf_counter() - self._started
        self.phases.append(
            {"phase": self._active, "seconds": round(elapsed, 3)}
        )
        self._active = None

    @property
    def total_seconds(self) -> float:
        self.stop()
        if self.phases:
            return round(sum(p["seconds"] for p in self.phases), 3)
        return round(time.perf_counter() - self._run_started, 3)


def _model_chat_rates(model: str) -> tuple[float, float]:
    settings = get_settings()
    if settings.llm_input_usd_per_1m is not None and settings.llm_output_usd_per_1m is not None:
        return (settings.llm_input_usd_per_1m, settings.llm_output_usd_per_1m)
    key = (model or "").strip().lower()
    for name, rates in _DEFAULT_MODEL_RATES.items():
        if name in key or key.startswith(name):
            return rates
    # Fallback: treat unknown chat models as gpt-5.4-mini-ish
    return _DEFAULT_MODEL_RATES["gpt-5.4-mini"]


def _model_embedding_rate(model: str) -> float:
    settings = get_settings()
    if settings.embedding_usd_per_1m is not None:
        return settings.embedding_usd_per_1m
    key = (model or "").strip().lower()
    for name, rate in _DEFAULT_EMBEDDING_RATES.items():
        if name in key or key.startswith(name):
            return rate
    return _DEFAULT_EMBEDDING_RATES["text-embedding-3-small"]


def estimate_cost_usd(bucket: UsageBucket) -> float:
    total = 0.0
    for model, counts in bucket.by_model.items():
        inp, out = _model_chat_rates(model)
        emb = _model_embedding_rate(model)
        total += counts.get("prompt", 0) * inp / 1_000_000
        total += counts.get("completion", 0) * out / 1_000_000
        total += counts.get("embedding", 0) * emb / 1_000_000
    # Models with only global counters and empty by_model (shouldn't happen)
    if not bucket.by_model and bucket.total_tokens:
        inp, out = _model_chat_rates(get_settings().chat_model)
        emb = _model_embedding_rate(get_settings().embedding_model)
        total += bucket.prompt_tokens * inp / 1_000_000
        total += bucket.completion_tokens * out / 1_000_000
        total += bucket.embedding_tokens * emb / 1_000_000
    return round(total, 6)


def build_run_metrics(
    phases: list[dict[str, Any]],
    bucket: UsageBucket | None,
    *,
    total_seconds: float | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    usage = bucket or UsageBucket()
    secs = (
        round(total_seconds, 3)
        if total_seconds is not None
        else round(sum(p.get("seconds", 0) for p in phases), 3)
    )
    cost = estimate_cost_usd(usage)
    out: dict[str, Any] = {
        "total_seconds": secs,
        "phases": [{"phase": p["phase"], "seconds": p["seconds"]} for p in phases],
        "tokens": {
            "prompt": usage.prompt_tokens,
            "completion": usage.completion_tokens,
            "embedding": usage.embedding_tokens,
            "total": usage.total_tokens,
        },
        "cost_usd": cost,
        "cost_estimated": True,
    }
    if catalog is not None:
        out["catalog"] = catalog
    return out


def merge_metrics(
    ingest_phases: list[dict[str, Any]],
    pipeline_metrics: dict[str, Any] | None,
    bucket: UsageBucket,
) -> dict[str, Any]:
    """Combine ingest-phase timings with pipeline done.detail metrics."""
    pipe_phases = list((pipeline_metrics or {}).get("phases") or [])
    phases = [*ingest_phases, *pipe_phases]
    catalog = (pipeline_metrics or {}).get("catalog")
    return build_run_metrics(phases, bucket, catalog=catalog)
