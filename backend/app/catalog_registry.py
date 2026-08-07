"""Server-side catalog registry — disk is source of truth for catalog list/titles."""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from app.config import get_settings
from app.pipeline.paths import DEMO_TENANT, TenantPaths, ensure_tenant_dirs, sanitize_tenant_id

_STAMP_PREFIX = re.compile(r"^\d{14}_")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _tenants_root() -> Path:
    return get_settings().data_dir / "tenants"


def _count_products(paths: TenantPaths) -> int:
    if not paths.raw_catalog.exists():
        return 0
    n = 0
    with paths.raw_catalog.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _fast_product_count(paths: TenantPaths) -> int:
    """Prefer canonical file count over scanning raw JSONL when indexed."""
    if paths.canonical.exists():
        n = sum(1 for p in paths.canonical.glob("*.json") if p.is_file())
        if n > 0:
            return n
    return _count_products(paths)


def _has_content(paths: TenantPaths) -> bool:
    if paths.catalog_meta.exists():
        return True
    if paths.raw_catalog.exists() and paths.raw_catalog.stat().st_size > 0:
        return True
    if paths.raw_ingest.exists() and any(paths.raw_ingest.iterdir()):
        return True
    if paths.canonical.exists() and any(paths.canonical.glob("*.json")):
        return True
    return False


def _iter_tenant_ids() -> list[str]:
    root = _tenants_root()
    root.mkdir(parents=True, exist_ok=True)
    ids: list[str] = [DEMO_TENANT]
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        tid = sanitize_tenant_id(child.name)
        if tid == DEMO_TENANT:
            continue
        if child.name != tid:
            continue
        paths = TenantPaths.for_tenant(tid)
        if _has_content(paths):
            ids.append(tid)
    return ids


def _existing_titles() -> set[str]:
    """Titles only — reads catalog.json meta, never scans product JSONL."""
    titles: set[str] = set()
    for tid in _iter_tenant_ids():
        meta = read_meta(tid)
        if meta and meta.get("title"):
            titles.add(str(meta["title"]).strip().lower())
            continue
        if tid == DEMO_TENANT:
            titles.add("demo catalog")
    return titles


def _title_from_ingest(paths: TenantPaths) -> str | None:
    if not paths.raw_ingest.exists():
        return None
    files = sorted(
        (p for p in paths.raw_ingest.iterdir() if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    if not files:
        return None
    name = files[0].name
    name = _STAMP_PREFIX.sub("", name)
    stem = Path(name).stem.strip("._- ")
    return stem or None


def _fallback_title(tenant_id: str, product_count: int) -> str:
    short = tenant_id[-6:] if len(tenant_id) >= 6 else tenant_id
    if product_count > 0:
        return f"Catalog {short} ({product_count})"
    return f"Catalog {short}"


def read_meta(tenant_id: str) -> dict | None:
    paths = TenantPaths.for_tenant(tenant_id)
    if not paths.catalog_meta.exists():
        return None
    try:
        data = json.loads(paths.catalog_meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def write_meta(
    tenant_id: str,
    *,
    title: str,
    created_at: int | None = None,
    updated_at: int | None = None,
) -> dict:
    paths = ensure_tenant_dirs(tenant_id)
    now = _now_ms()
    existing = read_meta(paths.tenant_id)
    created = created_at
    if created is None:
        created = int(existing["createdAt"]) if existing and "createdAt" in existing else now
    updated = updated_at if updated_at is not None else now
    meta = {
        "id": paths.tenant_id,
        "title": title.strip() or _fallback_title(paths.tenant_id, 0),
        "createdAt": created,
        "updatedAt": updated,
    }
    paths.catalog_meta.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return meta


def ensure_meta(tenant_id: str, *, title: str | None = None) -> dict:
    """Ensure catalog.json exists; synthesize title for orphans if needed."""
    tid = sanitize_tenant_id(tenant_id)
    paths = ensure_tenant_dirs(tid)
    existing = read_meta(tid)
    if existing and existing.get("title"):
        return {
            "id": tid,
            "title": str(existing["title"]),
            "createdAt": int(existing.get("createdAt") or _now_ms()),
            "updatedAt": int(existing.get("updatedAt") or _now_ms()),
        }

    product_count = _count_products(paths)
    resolved = (title or "").strip()
    if not resolved:
        if tid == DEMO_TENANT:
            resolved = "Demo catalog"
        else:
            resolved = _title_from_ingest(paths) or _fallback_title(tid, product_count)
    return write_meta(tid, title=resolved)


def _entry_from_tenant(tenant_id: str) -> dict:
    paths = TenantPaths.for_tenant(tenant_id)
    meta = ensure_meta(tenant_id)
    return {
        "id": meta["id"],
        "title": meta["title"],
        "createdAt": meta["createdAt"],
        "updatedAt": meta["updatedAt"],
        "productCount": _fast_product_count(paths),
    }


def list_catalogs() -> list[dict]:
    ensure_meta(DEMO_TENANT, title="Demo catalog")
    return [_entry_from_tenant(tid) for tid in _iter_tenant_ids()]


def create_catalog(title: str) -> dict:
    tid = f"t_{uuid.uuid4().hex[:12]}"
    ensure_tenant_dirs(tid)
    now = _now_ms()
    resolved = (title or "").strip() or "New catalog"
    # Avoid colliding with an existing title by appending a suffix.
    existing_titles = _existing_titles()
    base = resolved
    if base.lower() in existing_titles:
        suffix = 2
        while f"{base} {suffix}".lower() in existing_titles:
            suffix += 1
        resolved = f"{base} {suffix}"
    write_meta(tid, title=resolved, created_at=now, updated_at=now)
    return {
        "id": tid,
        "title": resolved,
        "createdAt": now,
        "updatedAt": now,
        "productCount": 0,
    }


def rename_catalog(tenant_id: str, title: str) -> dict:
    tid = sanitize_tenant_id(tenant_id)
    if tid == DEMO_TENANT:
        raise ValueError("Demo catalog cannot be renamed")
    trimmed = title.strip()
    if not trimmed:
        raise ValueError("Title is required")
    paths = TenantPaths.for_tenant(tid)
    if not paths.root.exists() and not read_meta(tid):
        raise ValueError("Catalog not found")
    meta = ensure_meta(tid)
    write_meta(tid, title=trimmed, created_at=meta["createdAt"])
    return _entry_from_tenant(tid)
