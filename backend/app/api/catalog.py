"""Catalog ingest and product management."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.catalog_service import (
    create_from_form,
    ingest_text,
    iter_create_from_form,
    iter_ingest_text,
    list_products,
    validate_text,
)
from app.deps import get_tenant_id
from app.pipeline import run_pipeline as pipeline_runner
from app.pipeline.io_utils import ensure_data_dirs
from app.pipeline.progress import format_sse
from app.pipeline.review_store import pipeline_status
from app.schemas import (
    CreateProductRequest,
    IngestJobResponse,
    IngestTextRequest,
    IngestValidateResponse,
    ProductListItem,
    ProgressEvent,
    RawProduct,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])

_running: dict[str, bool] = {}
_last_summary: dict[str, str | None] = {}


def _sse_from_events(events: Iterator[ProgressEvent]) -> Iterator[str]:
    try:
        for event in events:
            yield format_sse(event)
    except Exception as e:
        yield format_sse(
            ProgressEvent(type="error", phase="done", message=str(e))
        )


@router.post("/products", response_model=IngestJobResponse)
def create_product(body: CreateProductRequest, tenant_id: str = Depends(get_tenant_id)):
    try:
        return create_from_form(tenant_id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/products/stream")
def create_product_stream(
    body: CreateProductRequest, tenant_id: str = Depends(get_tenant_id)
):
    if _running.get(tenant_id):
        raise HTTPException(409, "pipeline already running")

    def gen():
        _running[tenant_id] = True
        try:
            yield from _sse_from_events(iter_create_from_form(tenant_id, body))
        finally:
            _running[tenant_id] = False

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/products/raw", response_model=IngestJobResponse)
def create_raw_product(body: RawProduct, tenant_id: str = Depends(get_tenant_id)):
    from app.catalog_service import ingest_and_run

    try:
        return ingest_and_run(tenant_id, [body])
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/products", response_model=list[ProductListItem])
def get_products(tenant_id: str = Depends(get_tenant_id)):
    return list_products(tenant_id)


@router.get("/products/{product_id}")
def get_catalog_product(product_id: str, tenant_id: str = Depends(get_tenant_id)):
    paths = ensure_data_dirs(tenant_id)
    path = paths.canonical / f"{product_id}.json"
    if not path.exists():
        raise HTTPException(404, "product not found")
    import json

    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/ingest/text", response_model=IngestJobResponse)
def ingest_text_body(body: IngestTextRequest, tenant_id: str = Depends(get_tenant_id)):
    if not body.text.strip():
        raise HTTPException(400, "text is required")
    is_csv = (body.source_name or "").lower().endswith(".csv")
    try:
        return ingest_text(
            tenant_id, body.text, source_name=body.source_name or "paste", is_csv=is_csv
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/ingest/text/stream")
def ingest_text_stream(body: IngestTextRequest, tenant_id: str = Depends(get_tenant_id)):
    if not body.text.strip():
        raise HTTPException(400, "text is required")
    if _running.get(tenant_id):
        raise HTTPException(409, "pipeline already running")
    is_csv = (body.source_name or "").lower().endswith(".csv")

    def gen():
        _running[tenant_id] = True
        try:
            yield from _sse_from_events(
                iter_ingest_text(
                    tenant_id,
                    body.text,
                    source_name=body.source_name or "paste",
                    is_csv=is_csv,
                )
            )
        finally:
            _running[tenant_id] = False

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ingest/validate", response_model=IngestValidateResponse)
def validate_ingest(body: IngestTextRequest, tenant_id: str = Depends(get_tenant_id)):
    is_csv = (body.source_name or "").lower().endswith(".csv")
    return validate_text(body.text, source_name=body.source_name, is_csv=is_csv)


@router.post("/pipeline/run")
def catalog_pipeline_run(tenant_id: str = Depends(get_tenant_id)):
    if _running.get(tenant_id):
        return {"ok": False, "message": "pipeline already running"}
    _running[tenant_id] = True
    try:
        summary = pipeline_runner.run_all(tenant_id)
        _last_summary[tenant_id] = summary
        return {"ok": True, "summary": summary}
    finally:
        _running[tenant_id] = False


@router.post("/pipeline/run/stream")
def catalog_pipeline_run_stream(tenant_id: str = Depends(get_tenant_id)):
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


@router.get("/pipeline/status")
def catalog_pipeline_status(tenant_id: str = Depends(get_tenant_id)):
    paths = ensure_data_dirs(tenant_id)
    return pipeline_status(
        paths,
        last_run_summary=_last_summary.get(tenant_id),
        running=_running.get(tenant_id, False),
    )
