"""Tenant-scoped data paths and Qdrant collection names."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

DEMO_TENANT = "demo"


def sanitize_tenant_id(tenant_id: str | None) -> str:
    tid = (tenant_id or DEMO_TENANT).strip().lower()
    tid = re.sub(r"[^a-z0-9_]", "_", tid)[:64]
    return tid or DEMO_TENANT


@dataclass(frozen=True)
class TenantPaths:
    tenant_id: str
    root: Path
    catalog_meta: Path
    raw: Path
    raw_catalog: Path
    raw_ingest: Path
    staged: Path
    normalized: Path
    canonical: Path
    overrides: Path
    review_queue: Path
    hash_ledger: Path
    dead_letter: Path
    personas_dir: Path
    catalog_profile: Path
    evals_dir: Path
    evals_scenarios: Path
    evals_runs: Path
    evals_drafts: Path
    collection: str

    @staticmethod
    def for_tenant(tenant_id: str | None) -> TenantPaths:
        tid = sanitize_tenant_id(tenant_id)
        root = get_settings().data_dir / "tenants" / tid
        personas_dir = root / "personas"
        evals_dir = root / "evals"
        return TenantPaths(
            tenant_id=tid,
            root=root,
            catalog_meta=root / "catalog.json",
            raw=root / "raw",
            raw_catalog=root / "raw" / "catalog.jsonl",
            raw_ingest=root / "raw" / "ingest",
            staged=root / "staged",
            normalized=root / "normalized",
            canonical=root / "canonical",
            overrides=root / "overrides",
            review_queue=root / "review_queue.jsonl",
            hash_ledger=root / "hash_ledger.json",
            dead_letter=root / "dead_letter.jsonl",
            personas_dir=personas_dir,
            catalog_profile=personas_dir / "catalog_profile.yaml",
            evals_dir=evals_dir,
            evals_scenarios=evals_dir / "scenarios",
            evals_runs=evals_dir / "runs",
            evals_drafts=evals_dir / "drafts",
            collection=f"products_{tid}",
        )


def ensure_tenant_dirs(tenant_id: str | None) -> TenantPaths:
    paths = TenantPaths.for_tenant(tenant_id)
    for d in (
        paths.raw,
        paths.raw_ingest,
        paths.staged,
        paths.normalized,
        paths.canonical,
        paths.overrides,
        paths.personas_dir,
        paths.evals_scenarios,
        paths.evals_runs,
        paths.evals_drafts,
    ):
        d.mkdir(parents=True, exist_ok=True)
    return paths


def migrate_legacy_to_demo() -> bool:
    """Move global data/ layout into data/tenants/demo/ (one-time)."""
    settings = get_settings()
    legacy = settings.data_dir
    demo = TenantPaths.for_tenant(DEMO_TENANT)
    if demo.raw_catalog.exists():
        return False
    legacy_catalog = legacy / "raw" / "catalog.jsonl"
    if not legacy_catalog.exists():
        return False

    ensure_tenant_dirs(DEMO_TENANT)
    moves = [
        (legacy / "raw", demo.raw),
        (legacy / "staged", demo.staged),
        (legacy / "normalized", demo.normalized),
        (legacy / "canonical", demo.canonical),
        (legacy / "overrides", demo.overrides),
    ]
    for src, dst in moves:
        if src.exists() and not any(dst.iterdir()) if dst.exists() else True:
            if dst.exists():
                for child in src.iterdir():
                    target = dst / child.name
                    if not target.exists():
                        shutil.move(str(child), str(target))
            else:
                shutil.move(str(src), str(dst))

    for fname in ("review_queue.jsonl", "hash_ledger.json", "dead_letter.jsonl"):
        src = legacy / fname
        dst = demo.root / fname
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))

    demo.raw_ingest.mkdir(parents=True, exist_ok=True)
    return True
