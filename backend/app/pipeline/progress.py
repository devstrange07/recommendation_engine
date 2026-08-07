"""SSE progress helpers for pipeline thought-stream."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterator
from typing import Any

from app.schemas import ProgressEvent, ProgressPhase

ProgressCallback = Callable[[ProgressEvent], None] | None

_SENTINEL = object()


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


def iter_from_thread(
    factory: Callable[[], Iterator[ProgressEvent]],
) -> Iterator[ProgressEvent]:
    """Run a progress producer in one dedicated thread; yield events here.

    Keeps ContextVar set/reset (e.g. pipeline_usage) in a single Context so
    Starlette's SSE thread-pool resumes cannot reset a foreign token.
    """
    event_queue: queue.Queue[ProgressEvent | object] = queue.Queue()
    error: list[BaseException] = []

    def _run() -> None:
        try:
            for event in factory():
                event_queue.put(event)
        except BaseException as exc:  # noqa: BLE001 - re-raised on consumer side
            error.append(exc)
        finally:
            event_queue.put(_SENTINEL)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    try:
        while True:
            item = event_queue.get()
            if item is _SENTINEL:
                break
            assert isinstance(item, ProgressEvent)
            yield item
    finally:
        thread.join()
    if error:
        raise error[0]
