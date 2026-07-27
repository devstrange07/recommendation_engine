"""SSE progress helpers for pipeline thought-stream."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from app.schemas import ProgressEvent, ProgressPhase

ProgressCallback = Callable[[ProgressEvent], None] | None


def emit(
    on_progress: ProgressCallback,
    *,
    type: str,
    phase: ProgressPhase,
    message: str,
    detail: dict[str, Any] | None = None,
) -> None:
    if on_progress is None:
        return
    on_progress(
        ProgressEvent(type=type, phase=phase, message=message, detail=detail)  # type: ignore[arg-type]
    )


def format_sse(event: ProgressEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"


def iter_sse(events: Iterator[ProgressEvent]) -> Iterator[str]:
    for event in events:
        yield format_sse(event)
