"""Pipeline orchestrator CLI: python -m app.pipeline.run_pipeline"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator

from app.pipeline import s1_preprocess, s2_normalize, s3_merge, s4_index
from app.pipeline.io_utils import ensure_data_dirs
from app.pipeline.paths import DEMO_TENANT
from app.pipeline.progress import ProgressCallback
from app.schemas import ProgressEvent


def measure_flag_recall(tenant_id: str = DEMO_TENANT) -> dict:
    paths = ensure_data_dirs(tenant_id)
    manifest_path = paths.raw / "defect_manifest.json"
    if not manifest_path.exists():
        return {"skipped": True}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    defects = manifest.get("defects", [])
    defect_by_id: dict[str, set[str]] = {}
    for d in defects:
        defect_by_id.setdefault(d["product_id"], set()).add(d["defect"])

    defect_to_flag = {
        "contradiction": "contradiction",
        "missing_category": "cant_categorize",
        "plans_indistinguishable": "plans_indistinguishable",
        "suspected_duplicate": "suspected_duplicate",
        "html_fluff": None,
    }

    flagged_ids: dict[str, set[str]] = {}
    for path in paths.normalized.glob("*.json"):
        rec = json.loads(path.read_text(encoding="utf-8"))
        types = {f["type"] for f in rec.get("flags", [])}
        if types:
            flagged_ids[rec["product_id"]] = types

    injectable = [d for d in defects if defect_to_flag.get(d["defect"])]
    hit = 0
    for d in injectable:
        expected = defect_to_flag[d["defect"]]
        if expected and expected in flagged_ids.get(d["product_id"], set()):
            hit += 1
        elif expected == "cant_categorize" and (
            "cant_categorize" in flagged_ids.get(d["product_id"], set())
            or "missing_required" in flagged_ids.get(d["product_id"], set())
        ):
            hit += 1

    clean_ids = {
        p.stem
        for p in paths.staged.glob("*.json")
        if p.stem not in defect_by_id
    }
    false_flags = sum(1 for pid in clean_ids if pid in flagged_ids)
    recall = (hit / len(injectable)) if injectable else 0.0
    false_rate = (false_flags / len(clean_ids)) if clean_ids else 0.0
    return {
        "injectable_defects": len(injectable),
        "flagged_hits": hit,
        "recall": round(recall, 3),
        "clean_products": len(clean_ids),
        "false_flagged": false_flags,
        "false_flag_rate": round(false_rate, 3),
        "target_recall": 0.70,
        "target_false_rate_max": 0.15,
    }


def iter_pipeline_progress(
    tenant_id: str = DEMO_TENANT,
    *,
    skip_normalize: bool = False,
    force_reembed: bool = False,
) -> Iterator[ProgressEvent]:
    """Yield phase/subtask events while running s1→s4. Final event is type=done."""
    ensure_data_dirs(tenant_id)
    parts = [f"tenant={tenant_id}"]

    yield ProgressEvent(
        type="phase_start",
        phase="preprocess",
        message="Starting preprocess",
    )
    yield ProgressEvent(
        type="subtask",
        phase="preprocess",
        message="Loading raw catalog",
    )
    yield ProgressEvent(
        type="subtask",
        phase="preprocess",
        message="Cleaning and staging products",
    )
    s1 = s1_preprocess.run(tenant_id)
    parts.append(f"s1={s1}")
    yield ProgressEvent(
        type="phase_done",
        phase="preprocess",
        message=(
            f"Staged {s1.get('staged', 0)} products"
            + (f", {s1.get('dead_letter', 0)} dead-lettered" if s1.get("dead_letter") else "")
        ),
        detail=s1,
    )

    if not skip_normalize:
        yield ProgressEvent(
            type="phase_start",
            phase="normalize",
            message="Starting normalize",
        )
        yield ProgressEvent(
            type="subtask",
            phase="normalize",
            message="Running LLM normalization",
        )
        s2 = s2_normalize.run(tenant_id)
        parts.append(f"s2={s2}")
        yield ProgressEvent(
            type="phase_done",
            phase="normalize",
            message=(
                f"Normalized {s2.get('normalized', 0)}"
                f", skipped {s2.get('skipped_unchanged', 0)}"
                f", flagged {s2.get('flags_queued', 0)}"
            ),
            detail=s2,
        )
    else:
        parts.append("s2=skipped")
        yield ProgressEvent(
            type="phase_start",
            phase="normalize",
            message="Normalize skipped",
        )
        yield ProgressEvent(
            type="phase_done",
            phase="normalize",
            message="Skipped",
            detail={"skipped": True},
        )

    yield ProgressEvent(
        type="phase_start",
        phase="merge",
        message="Starting merge",
    )
    yield ProgressEvent(
        type="subtask",
        phase="merge",
        message="Merging staged + normalized + overrides",
    )
    s3 = s3_merge.run(tenant_id)
    parts.append(f"s3={s3}")
    yield ProgressEvent(
        type="phase_done",
        phase="merge",
        message=f"Wrote {s3.get('canonical', 0)} canonical products",
        detail=s3,
    )

    yield ProgressEvent(
        type="phase_start",
        phase="index",
        message="Starting index",
    )
    yield ProgressEvent(
        type="subtask",
        phase="index",
        message="Embedding products",
    )
    yield ProgressEvent(
        type="subtask",
        phase="index",
        message="Upserting to Qdrant",
    )
    s4 = s4_index.run(tenant_id, force_all=force_reembed)
    parts.append(f"s4={s4}")
    yield ProgressEvent(
        type="phase_done",
        phase="index",
        message=(
            f"Upserted {s4.get('upserted', 0)} points"
            f" into {s4.get('collection', 'qdrant')}"
        ),
        detail=s4,
    )

    if tenant_id == DEMO_TENANT:
        recall = measure_flag_recall(tenant_id)
        parts.append(f"flag_metrics={recall}")

    summary = " | ".join(parts)
    print(summary)
    yield ProgressEvent(
        type="done",
        phase="done",
        message="Pipeline complete",
        detail={"ok": True, "summary": summary},
    )


def run_all(
    tenant_id: str = DEMO_TENANT,
    *,
    skip_normalize: bool = False,
    force_reembed: bool = False,
    on_progress: ProgressCallback = None,
) -> str:
    summary = ""
    for event in iter_pipeline_progress(
        tenant_id,
        skip_normalize=skip_normalize,
        force_reembed=force_reembed,
    ):
        if on_progress:
            on_progress(event)
        if event.type == "done" and event.detail:
            summary = str(event.detail.get("summary") or "")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default=DEMO_TENANT)
    parser.add_argument("--skip-normalize", action="store_true")
    parser.add_argument("--force-reembed", action="store_true")
    args = parser.parse_args()
    run_all(
        args.tenant,
        skip_normalize=args.skip_normalize,
        force_reembed=args.force_reembed,
    )


if __name__ == "__main__":
    main()
