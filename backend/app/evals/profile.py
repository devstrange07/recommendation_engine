"""Generate catalog_profile.yaml from canonical products."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.openai_client import call_with_forced_tool, chat_key_present
from app.pipeline.paths import TenantPaths, ensure_tenant_dirs


class SoftExpectations(BaseModel):
    in_scope_domains: list[str] = Field(default_factory=list)
    out_of_scope_domains: list[str] = Field(default_factory=list)
    notable_facets: list[str] = Field(default_factory=list)
    typical_constraints: list[str] = Field(default_factory=list)


class SoftExpectationsOut(BaseModel):
    overview: str
    soft_expectations: SoftExpectations


def _load_canonical(paths: TenantPaths) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    if not paths.canonical.exists():
        return products
    for p in sorted(paths.canonical.glob("*.json")):
        try:
            products.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return products


def aggregate_catalog_stats(products: list[dict[str, Any]]) -> dict[str, Any]:
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prod in products:
        cat = prod.get("category_path") or "Unknown"
        by_cat[cat].append(prod)

    domains: list[dict[str, Any]] = []
    for cat, items in sorted(by_cat.items(), key=lambda x: (-len(x[1]), x[0])):
        kinds = sorted({str(i.get("kind") or "") for i in items if i.get("kind")})
        brands = Counter()
        facet_keys: set[str] = set()
        tags: Counter[str] = Counter()
        price_mins: dict[str, list[float]] = defaultdict(list)
        for i in items:
            b = i.get("brand") or i.get("brand_or_provider") or i.get("provider")
            if b:
                brands[str(b)] += 1
            for t in i.get("use_case_tags") or []:
                tags[str(t)] += 1
            for f in i.get("facets") or []:
                if isinstance(f, dict) and f.get("key"):
                    facet_keys.add(str(f["key"]))
            for attrs in (i.get("attributes") or {}).keys() if isinstance(i.get("attributes"), dict) else []:
                facet_keys.add(str(attrs))
            pmin = i.get("price_min") or {}
            if isinstance(pmin, dict):
                for cur, amt in pmin.items():
                    try:
                        price_mins[str(cur)].append(float(amt))
                    except (TypeError, ValueError):
                        pass

        price_ranges = {}
        for cur, vals in price_mins.items():
            if vals:
                price_ranges[cur] = {"min": min(vals), "max": max(vals)}

        sample_titles = [str(i.get("title") or i.get("id")) for i in items[:5]]
        domains.append(
            {
                "category_path": cat,
                "count": len(items),
                "kinds": kinds,
                "brands": [b for b, _ in brands.most_common(8)],
                "top_tags": [t for t, _ in tags.most_common(8)],
                "price_ranges": price_ranges,
                "facet_keys": sorted(facet_keys),
                "sample_titles": sample_titles,
            }
        )

    return {
        "product_count": len(products),
        "domains": domains,
        "category_paths": [d["category_path"] for d in domains],
    }


def catalog_run_stats(products: list[dict[str, Any]]) -> dict[str, int]:
    """Compact catalog snapshot for pipeline run metrics."""
    stats = aggregate_catalog_stats(products)
    brands: set[str] = set()
    for prod in products:
        b = prod.get("brand") or prod.get("brand_or_provider") or prod.get("provider")
        if b:
            brands.add(str(b))
    return {
        "product_count": int(stats.get("product_count") or 0),
        "category_count": len(stats.get("category_paths") or []),
        "brand_count": len(brands),
    }


def catalog_run_stats_for_tenant(tenant_id: str) -> dict[str, int]:
    paths = ensure_tenant_dirs(tenant_id)
    return catalog_run_stats(_load_canonical(paths))


def _heuristic_soft(stats: dict[str, Any]) -> SoftExpectationsOut:
    cats = stats.get("category_paths") or []
    facet_keys: list[str] = []
    for d in stats.get("domains") or []:
        facet_keys.extend(d.get("facet_keys") or [])
    notable = sorted(set(facet_keys))[:12]
    overview = (
        f"Catalog with {stats.get('product_count', 0)} products across "
        f"{len(cats)} category path(s): {', '.join(cats[:8])}."
    )
    return SoftExpectationsOut(
        overview=overview,
        soft_expectations=SoftExpectations(
            in_scope_domains=cats,
            out_of_scope_domains=[],
            notable_facets=notable,
            typical_constraints=["budget", "category", "brand"] if cats else [],
        ),
    )


def _llm_soft(stats: dict[str, Any]) -> SoftExpectationsOut:
    compact = {
        "product_count": stats.get("product_count"),
        "domains": [
            {
                "category_path": d["category_path"],
                "count": d["count"],
                "kinds": d["kinds"],
                "brands": d["brands"][:5],
                "facet_keys": d["facet_keys"][:10],
                "sample_titles": d["sample_titles"][:3],
                "price_ranges": d.get("price_ranges"),
            }
            for d in (stats.get("domains") or [])[:20]
        ],
    }
    return call_with_forced_tool(
        messages=[
            {
                "role": "system",
                "content": (
                    "You summarize a product catalog for retrieval evaluation. "
                    "Write a short overview and soft_expectations (no product IDs). "
                    "in_scope_domains = category paths present. "
                    "out_of_scope_domains = plausible wrong verticals an agent might confuse. "
                    "notable_facets = filterable attributes shoppers would mention. "
                    "typical_constraints = common shopping constraints for this catalog."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(compact, ensure_ascii=False),
            },
        ],
        tool_name="submit_catalog_profile",
        tool_description="Submit catalog overview and soft expectations",
        parameters_model=SoftExpectationsOut,
        validate=SoftExpectationsOut.model_validate,
    )


def generate_catalog_profile(tenant_id: str) -> dict[str, Any]:
    """Aggregate canonical products, enrich with LLM soft expectations, write YAML."""
    paths = ensure_tenant_dirs(tenant_id)
    products = _load_canonical(paths)
    stats = aggregate_catalog_stats(products)

    if chat_key_present() and products:
        try:
            soft = _llm_soft(stats)
        except Exception as e:
            print(f"WARN: catalog_profile LLM soft expectations failed: {e}")
            soft = _heuristic_soft(stats)
    else:
        soft = _heuristic_soft(stats)

    doc: dict[str, Any] = {
        "version": 1,
        "tenant_id": paths.tenant_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "canonical_aggregate",
        "product_count": stats["product_count"],
        "domains": stats["domains"],
        "overview": soft.overview,
        "soft_expectations": soft.soft_expectations.model_dump(),
    }
    paths.personas_dir.mkdir(parents=True, exist_ok=True)
    paths.catalog_profile.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return doc


def load_catalog_profile(tenant_id: str) -> dict[str, Any] | None:
    paths = TenantPaths.for_tenant(tenant_id)
    if not paths.catalog_profile.exists():
        return None
    return yaml.safe_load(paths.catalog_profile.read_text(encoding="utf-8"))
