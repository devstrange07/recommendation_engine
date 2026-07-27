"""Review queue + overrides + pipeline status helpers."""

from __future__ import annotations

import json

from app.pipeline.io_utils import ensure_data_dirs, read_jsonl, write_json
from app.pipeline.paths import TenantPaths
from app.schemas import OverrideAnswer, PipelineStatus, ReviewFlagItem


def load_queue(paths: TenantPaths) -> list[ReviewFlagItem]:
    items = []
    for row in read_jsonl(paths.review_queue):
        items.append(ReviewFlagItem.model_validate(row))
    return items


def replace_queue(paths: TenantPaths, items: list[ReviewFlagItem]) -> None:
    paths.review_queue.parent.mkdir(parents=True, exist_ok=True)
    with paths.review_queue.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")


def load_overrides(paths: TenantPaths, product_id: str) -> dict:
    path = paths.overrides / f"{product_id}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_override(paths: TenantPaths, answer: OverrideAnswer) -> None:
    path = paths.overrides / f"{answer.product_id}.json"
    existing = load_overrides(paths, answer.product_id)
    fields = existing.get("fields", {})
    fields[answer.field] = {
        "value": answer.value,
        "flag_type": answer.flag_type,
    }
    write_json(path, {"product_id": answer.product_id, "fields": fields})
    remaining = [
        q
        for q in load_queue(paths)
        if not (q.product_id == answer.product_id and q.flag.field == answer.field)
    ]
    replace_queue(paths, remaining)


def pipeline_status(
    paths: TenantPaths,
    *,
    last_run_summary: str | None,
    running: bool,
) -> PipelineStatus:
    root = paths.root
    counts = {
        "raw": 1 if paths.raw_catalog.exists() else 0,
        "staged": len(list(paths.staged.glob("*.json"))),
        "normalized": len(list(paths.normalized.glob("*.json"))),
        "canonical": len(list(paths.canonical.glob("*.json"))),
        "review_queue": len(load_queue(paths)),
        "running": 1 if running else 0,
    }
    pending = sum(
        1
        for p in paths.canonical.glob("*.json")
        if json.loads(p.read_text(encoding="utf-8")).get("review_pending")
    )
    return PipelineStatus(
        stage_counts=counts,
        review_pending_count=pending,
        last_run_summary=last_run_summary,
    )
