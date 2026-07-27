"""Admin / pipeline endpoints."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.deps import get_tenant_id
from app.pipeline import run_pipeline as pipeline_runner
from app.pipeline.io_utils import ensure_data_dirs
from app.pipeline.progress import format_sse
from app.pipeline.review_store import pipeline_status
from app.schemas import PipelineStatus, ProgressEvent

router = APIRouter()

_last_summary: dict[str, str | None] = {}
_running: dict[str, bool] = {}


def _run(tenant_id: str):
    global _last_summary, _running
    _running[tenant_id] = True
    try:
        summary = pipeline_runner.run_all(tenant_id)
        _last_summary[tenant_id] = summary
    finally:
        _running[tenant_id] = False


@router.post("/pipeline/run")
def pipeline_run(
    background_tasks: BackgroundTasks,
    sync: bool = False,
    tenant_id: str = Depends(get_tenant_id),
):
    if _running.get(tenant_id):
        return {"ok": False, "message": "pipeline already running"}
    if sync:
        summary = pipeline_runner.run_all(tenant_id)
        _last_summary[tenant_id] = summary
        return {"ok": True, "summary": summary}
    background_tasks.add_task(_run, tenant_id)
    return {"ok": True, "message": "pipeline started"}


@router.post("/pipeline/run/stream")
def pipeline_run_stream(tenant_id: str = Depends(get_tenant_id)):
    if _running.get(tenant_id):
        raise HTTPException(409, "pipeline already running")

    def gen():
        _running[tenant_id] = True
        try:
            for event in pipeline_runner.iter_pipeline_progress(tenant_id):
                if event.type == "done" and event.detail:
                    _last_summary[tenant_id] = event.detail.get("summary")
                yield format_sse(event)
        except Exception as e:
            yield format_sse(
                ProgressEvent(type="error", phase="done", message=str(e))
            )
        finally:
            _running[tenant_id] = False

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/pipeline/status", response_model=PipelineStatus)
def pipeline_status_route(tenant_id: str = Depends(get_tenant_id)):
    paths = ensure_data_dirs(tenant_id)
    return pipeline_status(
        paths,
        last_run_summary=_last_summary.get(tenant_id),
        running=_running.get(tenant_id, False),
    )
