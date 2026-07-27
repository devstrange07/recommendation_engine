"""JSONL / path helpers for pipeline stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel

from app.pipeline.paths import TenantPaths, ensure_tenant_dirs, migrate_legacy_to_demo

T = TypeVar("T", bound=BaseModel)


def ensure_data_dirs(tenant_id: str | None = None) -> TenantPaths:
    migrate_legacy_to_demo()
    return ensure_tenant_dirs(tenant_id or "demo")


def write_jsonl(path: Path, items: Iterable[BaseModel | dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            if isinstance(item, BaseModel):
                f.write(item.model_dump_json() + "\n")
            else:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, item: BaseModel | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        if isinstance(item, BaseModel):
            f.write(item.model_dump_json() + "\n")
        else:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def load_hash_ledger(paths: TenantPaths) -> dict[str, str]:
    if not paths.hash_ledger.exists():
        return {}
    return json.loads(paths.hash_ledger.read_text(encoding="utf-8"))


def save_hash_ledger(paths: TenantPaths, ledger: dict[str, str]) -> None:
    paths.hash_ledger.parent.mkdir(parents=True, exist_ok=True)
    paths.hash_ledger.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def write_json(path: Path, data: BaseModel | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, BaseModel):
        path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
