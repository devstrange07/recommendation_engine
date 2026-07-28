"""Catalog product creation, listing, and ingest orchestration."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from app.catalog_registry import ensure_meta
from app.pipeline import run_pipeline
from app.pipeline.io_utils import append_jsonl, ensure_data_dirs, load_hash_ledger, read_jsonl
from app.pipeline.paths import TenantPaths
from app.pipeline.progress import ProgressCallback
from app.pipeline.review_store import load_queue
from app.pipeline.s0_ingest import extract_products, parse_csv_text
from app.pipeline.s4_index import get_qdrant
from app.schemas import (
    CreatePlanRequest,
    CreateProductRequest,
    IngestJobResponse,
    IngestValidateResponse,
    ProductIngestResult,
    ProductListItem,
    ProgressEvent,
    RawPlan,
    RawPriceList,
    RawProduct,
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_product_id() -> str:
    return f"user_{uuid.uuid4().hex[:8]}"


def create_product_request_to_raw(req: CreateProductRequest) -> RawProduct:
    plans: list[RawPlan] = []
    for i, plan in enumerate(req.plans, start=1):
        price_lists = [
            RawPriceList(
                name=f"{plan.name} — {p.country}",
                country=p.country,
                currency=p.currency,
                amount=p.amount,
            )
            for p in plan.prices
        ]
        plans.append(
            RawPlan(
                id=f"plan_{i}",
                name=plan.name,
                feature_text=plan.feature_text,
                billing_period=plan.billing_period,
                price_lists=price_lists,
            )
        )
    return RawProduct(
        id=_new_product_id(),
        name=req.name,
        category=req.category,
        description=req.description,
        plans=plans,
        updated_at=_now_iso(),
    )


def append_products(paths: TenantPaths, products: list[RawProduct]) -> list[str]:
    existing_ids = {row.get("id") for row in read_jsonl(paths.raw_catalog)}
    added: list[str] = []
    for product in products:
        if product.id in existing_ids:
            raise ValueError(f"Product id already exists: {product.id}")
        append_jsonl(paths.raw_catalog, product)
        existing_ids.add(product.id)
        added.append(product.id)
    return added


def _dead_letter_ids(paths: TenantPaths) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for row in read_jsonl(paths.dead_letter):
        pid = row.get("product_id")
        if pid:
            reasons[pid] = row.get("reason", "failed")
    return reasons


def _product_status(paths: TenantPaths, product_id: str, name: str) -> ProductIngestResult:
    dead = _dead_letter_ids(paths)
    if product_id in dead:
        return ProductIngestResult(
            product_id=product_id,
            name=name,
            status="failed",
            error=dead[product_id],
        )

    flags = [q.flag.type for q in load_queue(paths) if q.product_id == product_id]
    canon_path = paths.canonical / f"{product_id}.json"
    if canon_path.exists():
        data = json.loads(canon_path.read_text(encoding="utf-8"))
        ledger = load_hash_ledger(paths)
        indexed = ledger.get(product_id) == data.get("content_hash")
        if data.get("review_pending") or flags:
            return ProductIngestResult(
                product_id=product_id,
                name=name,
                status="flagged",
                flags=flags or ["review_pending"],
            )
        if indexed:
            return ProductIngestResult(
                product_id=product_id,
                name=data.get("title", name),
                status="indexed",
            )
        return ProductIngestResult(product_id=product_id, name=name, status="processing")

    staged = paths.staged / f"{product_id}.json"
    if staged.exists():
        return ProductIngestResult(product_id=product_id, name=name, status="processing")

    return ProductIngestResult(product_id=product_id, name=name, status="pending")


def list_products(tenant_id: str) -> list[ProductListItem]:
    paths = ensure_data_dirs(tenant_id)
    items: list[ProductListItem] = []
    for row in read_jsonl(paths.raw_catalog):
        pid = row.get("id", "")
        name = row.get("name", pid)
        result = _product_status(paths, pid, name)
        items.append(
            ProductListItem(
                product_id=result.product_id,
                name=result.name,
                status=result.status,
                flags=result.flags,
            )
        )
    return items


def iter_ingest_and_run(
    tenant_id: str,
    products: list[RawProduct],
    *,
    run_pipeline_after: bool = True,
    ingest_mode: str = "append",
) -> Iterator[ProgressEvent]:
    """Yield ingest + pipeline progress; final done.detail is IngestJobResponse dict."""
    paths = ensure_data_dirs(tenant_id)
    ensure_meta(tenant_id)
    if not products:
        raise ValueError("No products to ingest")

    id_to_name = {p.id: p.name for p in products}

    yield ProgressEvent(type="phase_start", phase="ingest", message="Starting ingest")
    if ingest_mode == "append":
        yield ProgressEvent(
            type="subtask",
            phase="ingest",
            message=f"Appending {len(products)} product(s) to raw catalog",
        )
    append_products(paths, products)
    yield ProgressEvent(
        type="phase_done",
        phase="ingest",
        message=f"Wrote {len(products)} product(s) to raw catalog",
        detail={"count": len(products)},
    )

    summary = None
    if run_pipeline_after:
        for event in run_pipeline.iter_pipeline_progress(tenant_id):
            if event.type == "done":
                summary = (event.detail or {}).get("summary")
                continue
            yield event

    results = [_product_status(paths, pid, id_to_name[pid]) for pid in id_to_name]
    response = IngestJobResponse(
        tenant_id=paths.tenant_id,
        products=results,
        pipeline_summary=summary,
    )
    yield ProgressEvent(
        type="done",
        phase="done",
        message="Ingest complete",
        detail=response.model_dump(),
    )


def ingest_and_run(
    tenant_id: str,
    products: list[RawProduct],
    *,
    run_pipeline_after: bool = True,
    on_progress: ProgressCallback = None,
) -> IngestJobResponse:
    response: IngestJobResponse | None = None
    for event in iter_ingest_and_run(
        tenant_id, products, run_pipeline_after=run_pipeline_after
    ):
        if on_progress:
            on_progress(event)
        if event.type == "done" and event.detail:
            response = IngestJobResponse.model_validate(event.detail)
    if response is None:
        raise RuntimeError("Ingest produced no result")
    return response


def create_from_form(
    tenant_id: str,
    req: CreateProductRequest,
    *,
    on_progress: ProgressCallback = None,
) -> IngestJobResponse:
    raw = create_product_request_to_raw(req)
    return ingest_and_run(tenant_id, [raw], on_progress=on_progress)


def iter_create_from_form(
    tenant_id: str, req: CreateProductRequest
) -> Iterator[ProgressEvent]:
    raw = create_product_request_to_raw(req)
    yield from iter_ingest_and_run(tenant_id, [raw])


def _try_create_product_json(text: str) -> list[RawProduct] | None:
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "name" in data and "plans" in data:
            req = CreateProductRequest.model_validate(data)
            return [create_product_request_to_raw(req)]
    except Exception:
        return None
    return None


def validate_text(text: str, *, source_name: str | None = None, is_csv: bool = False) -> IngestValidateResponse:
    errors: list[str] = []
    try:
        structured = _try_create_product_json(text)
        if structured is not None:
            products = structured
        elif is_csv:
            products = parse_csv_text(text)
        else:
            products = extract_products(text, source_name=source_name)
    except Exception as e:
        return IngestValidateResponse(valid=False, errors=[str(e)])

    if not products:
        return IngestValidateResponse(valid=False, errors=["No products extracted"])

    results: list[ProductIngestResult] = []
    for p in products:
        try:
            RawProduct.model_validate(p.model_dump())
            results.append(
                ProductIngestResult(product_id=p.id, name=p.name, status="pending")
            )
        except Exception as e:
            errors.append(f"{p.name}: {e}")

    return IngestValidateResponse(valid=len(errors) == 0, products=results, errors=errors)


def _parse_ingest_text(
    text: str,
    *,
    source_name: str | None = None,
    is_csv: bool = False,
) -> tuple[list[RawProduct], str]:
    """Return (products, format_label)."""
    structured = _try_create_product_json(text)
    if structured is not None:
        return structured, "structured JSON"
    if is_csv:
        return parse_csv_text(text), "CSV"
    from app.pipeline.s0_ingest import _parse_structured

    catalog_json = _parse_structured(text)
    if catalog_json is not None:
        return catalog_json, "catalog JSON"
    return extract_products(text, source_name=source_name), "text / LLM extract"


def iter_ingest_text(
    tenant_id: str,
    text: str,
    *,
    source_name: str | None = None,
    is_csv: bool = False,
    audit_path: str | None = None,
) -> Iterator[ProgressEvent]:
    paths = ensure_data_dirs(tenant_id)
    if audit_path:
        audit_file = paths.raw_ingest / audit_path
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        audit_file.write_text(text, encoding="utf-8")

    yield ProgressEvent(type="phase_start", phase="ingest", message="Starting ingest")
    yield ProgressEvent(
        type="subtask",
        phase="ingest",
        message="Detecting input format",
    )
    products, fmt = _parse_ingest_text(text, source_name=source_name, is_csv=is_csv)
    yield ProgressEvent(
        type="subtask",
        phase="ingest",
        message=f"Parsed as {fmt} — {len(products)} product(s)",
        detail={"format": fmt, "count": len(products)},
    )
    if not products:
        raise ValueError("No products to ingest")

    id_to_name = {p.id: p.name for p in products}
    yield ProgressEvent(
        type="subtask",
        phase="ingest",
        message=f"Appending {len(products)} product(s) to raw catalog",
    )
    append_products(paths, products)
    yield ProgressEvent(
        type="phase_done",
        phase="ingest",
        message=f"Wrote {len(products)} product(s) to raw catalog",
        detail={"count": len(products), "format": fmt},
    )

    summary = None
    for event in run_pipeline.iter_pipeline_progress(tenant_id):
        if event.type == "done":
            summary = (event.detail or {}).get("summary")
            continue
        yield event

    results = [_product_status(paths, pid, id_to_name[pid]) for pid in id_to_name]
    response = IngestJobResponse(
        tenant_id=paths.tenant_id,
        products=results,
        pipeline_summary=summary,
    )
    yield ProgressEvent(
        type="done",
        phase="done",
        message="Ingest complete",
        detail=response.model_dump(),
    )


def ingest_text(
    tenant_id: str,
    text: str,
    *,
    source_name: str | None = None,
    is_csv: bool = False,
    audit_path: str | None = None,
    on_progress: ProgressCallback = None,
) -> IngestJobResponse:
    response: IngestJobResponse | None = None
    for event in iter_ingest_text(
        tenant_id,
        text,
        source_name=source_name,
        is_csv=is_csv,
        audit_path=audit_path,
    ):
        if on_progress:
            on_progress(event)
        if event.type == "done" and event.detail:
            response = IngestJobResponse.model_validate(event.detail)
    if response is None:
        raise RuntimeError("Ingest produced no result")
    return response


def save_upload_audit(paths: TenantPaths, filename: str, content: bytes) -> Path:
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File exceeds {MAX_UPLOAD_BYTES // 1024 // 1024}MB limit")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[:120]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    dest = paths.raw_ingest / f"{stamp}_{safe}"
    dest.write_bytes(content)
    return dest


def iter_ingest_file(
    tenant_id: str,
    filename: str,
    content: bytes,
) -> Iterator[ProgressEvent]:
    """ETL pipeline for binary file uploads — extract, then feed existing catalog pipeline."""
    from app.pipeline.file_etl.detect import is_text_format, detect_format
    from app.pipeline.file_etl.extract import extract_file

    paths = ensure_data_dirs(tenant_id)
    save_upload_audit(paths, filename, content)
    stem = Path(filename).stem.strip() or None
    ensure_meta(tenant_id, title=stem)

    yield ProgressEvent(type="phase_start", phase="ingest", message="Starting file ingest")

    fmt = detect_format(filename)
    if fmt is None:
        raise ValueError(f"Unsupported file type: {filename}")

    progress_messages: list[str] = []

    def _on_progress(msg: str) -> None:
        progress_messages.append(msg)

    if is_text_format(fmt):
        yield ProgressEvent(type="subtask", phase="ingest", message=f"Detected text format ({fmt})")
        text = content.decode("utf-8", errors="replace")
        is_csv = filename.lower().endswith((".csv", ".tsv"))
        products, fmt_label = _parse_ingest_text(text, source_name=filename, is_csv=is_csv)
        yield ProgressEvent(
            type="subtask",
            phase="ingest",
            message=f"Parsed as {fmt_label} — {len(products)} product(s)",
            detail={"format": fmt_label, "count": len(products)},
        )
    else:
        doc = extract_file(content, filename, on_progress=_on_progress)
        for msg in progress_messages:
            yield ProgressEvent(type="subtask", phase="ingest", message=msg)

        prompt_text = doc.to_prompt_text()
        if not prompt_text.strip():
            raise ValueError("No extractable content found in file")

        yield ProgressEvent(
            type="subtask",
            phase="ingest",
            message="Extracting products via LLM…",
            detail=doc.stats.to_dict(),
        )
        products = extract_products(prompt_text, source_name=filename)
        yield ProgressEvent(
            type="subtask",
            phase="ingest",
            message=f"LLM extracted {len(products)} product(s)",
            detail={"count": len(products)},
        )

    if not products:
        raise ValueError("No products extracted from file")

    id_to_name = {p.id: p.name for p in products}
    yield ProgressEvent(
        type="subtask",
        phase="ingest",
        message=f"Appending {len(products)} product(s) to raw catalog",
    )
    append_products(paths, products)
    yield ProgressEvent(
        type="phase_done",
        phase="ingest",
        message=f"Wrote {len(products)} product(s) to raw catalog",
        detail={"count": len(products)},
    )

    summary = None
    for event in run_pipeline.iter_pipeline_progress(tenant_id):
        if event.type == "done":
            summary = (event.detail or {}).get("summary")
            continue
        yield event

    results = [_product_status(paths, pid, id_to_name[pid]) for pid in id_to_name]
    response = IngestJobResponse(
        tenant_id=paths.tenant_id,
        products=results,
        pipeline_summary=summary,
    )
    yield ProgressEvent(
        type="done",
        phase="done",
        message="Ingest complete",
        detail=response.model_dump(),
    )


def delete_catalog(tenant_id: str) -> dict[str, object]:
    paths = TenantPaths.for_tenant(tenant_id)
    client = get_qdrant()
    collection_deleted = False
    tenant_deleted = False
    try:
        existing = {c.name for c in client.get_collections().collections}
        if paths.collection in existing:
            client.delete_collection(collection_name=paths.collection)
            collection_deleted = True
    except Exception:
        # Treat backend vector-store errors as non-fatal for idempotent delete.
        pass

    if paths.root.exists():
        shutil.rmtree(paths.root, ignore_errors=False)
        tenant_deleted = True

    return {
        "ok": True,
        "tenant_id": paths.tenant_id,
        "collection": paths.collection,
        "collection_deleted": collection_deleted,
        "tenant_deleted": tenant_deleted,
    }
