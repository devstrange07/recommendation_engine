"""Hybrid search against Qdrant with fallback ladder."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.openai_client import embedding_model, get_openai
from app.pipeline.s4_index import get_qdrant
from app.schemas import FallbackDebug, HitDebug, SearchRequest

COUNTRY_CURRENCY = {"IN": "INR", "US": "USD", "GB": "GBP"}


def _has_openai_key() -> bool:
    key = get_settings().openai_api_key.strip()
    return bool(key) and key != "sk-your-key-here"


def _hash_embed(text: str, dim: int = 1536) -> list[float]:
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
        vec[(h // dim) % dim] += 0.5
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def _embed_query(text: str) -> list[float]:
    if not _has_openai_key():
        return _hash_embed(text)
    try:
        resp = get_openai().embeddings.create(model=embedding_model(), input=[text])
        return resp.data[0].embedding
    except Exception:
        return _hash_embed(text)


def _bm25_vector(text: str) -> models.SparseVector:
    tokens = [t.lower() for t in text.replace("/", " ").replace("-", " ").split() if len(t) > 1]
    tf: dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0.0) + 1.0
    indices, values = [], []
    for term, freq in tf.items():
        idx = int(hashlib.md5(term.encode()).hexdigest()[:8], 16) % 1_000_003
        indices.append(idx)
        values.append(freq)
    return models.SparseVector(indices=indices, values=values)


def _build_filter(
    req: SearchRequest,
    *,
    country: str,
    currency: str,
    price_max: float | None,
    use_tags: bool,
    use_category: bool = True,
) -> models.Filter | None:
    must: list[models.FieldCondition | models.Filter] = [
        models.FieldCondition(key="status", match=models.MatchValue(value="active")),
    ]
    if use_category and req.category_path:
        must.append(
            models.FieldCondition(key="category_path", match=models.MatchValue(value=req.category_path))
        )
    if use_tags and req.use_case_tags:
        must.append(
            models.FieldCondition(key="use_case_tags", match=models.MatchAny(any=req.use_case_tags))
        )
    if use_tags and req.target_audience:
        must.append(
            models.FieldCondition(
                key="target_audience", match=models.MatchAny(any=req.target_audience)
            )
        )
    if req.billing_period:
        must.append(
            models.FieldCondition(
                key="offerings[].billing_period",
                match=models.MatchValue(value=req.billing_period),
            )
        )
    if price_max is not None:
        # Filter: has a price for country with amount <= price_max
        must.append(
            models.FieldCondition(
                key="offerings[].prices[].country",
                match=models.MatchValue(value=country),
            )
        )
        must.append(
            models.FieldCondition(
                key="offerings[].prices[].amount",
                range=models.Range(lte=price_max),
            )
        )
    return models.Filter(must=must) if must else None


def _query(
    client: QdrantClient,
    collection: str,
    dense: list[float],
    sparse: models.SparseVector,
    query_filter: models.Filter | None,
    top_k: int,
) -> list[Any]:
    try:
        result = client.query_points(
            collection_name=collection,
            prefetch=[
                models.Prefetch(
                    query=dense,
                    using="dense",
                    filter=query_filter,
                    limit=max(top_k * 3, 20),
                ),
                models.Prefetch(
                    query=sparse,
                    using="bm25",
                    filter=query_filter,
                    limit=max(top_k * 3, 20),
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        return result.points
    except Exception as first_err:
        err = str(first_err).lower()
        if "doesn't exist" in err or "not found" in err:
            return []
        try:
            result = client.query_points(
                collection_name=collection,
                query=dense,
                using="dense",
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
            return result.points
        except Exception:
            return []


def _passes_price(payload: dict[str, Any], *, country: str, currency: str, price_max: float | None) -> bool:
    if price_max is None:
        return True
    for o in payload.get("offerings") or []:
        for pr in o.get("prices") or []:
            if pr.get("country") == country and float(pr.get("amount", 1e18)) <= float(price_max):
                return True
    pmin = (payload.get("price_min") or {}).get(currency)
    return pmin is not None and float(pmin) <= float(price_max)


def search_products(
    req: SearchRequest,
    *,
    country: str = "IN",
    tenant_id: str = "demo",
) -> tuple[list[dict[str, Any]], dict[str, Any], FallbackDebug, list[HitDebug], float]:
    """Returns hits payloads, qdrant_query debug, fallback, hit debugs, latency_ms."""
    from app.pipeline.paths import TenantPaths

    t0 = time.perf_counter()
    paths = TenantPaths.for_tenant(tenant_id)
    client = get_qdrant()
    collection = paths.collection
    currency = COUNTRY_CURRENCY.get(country.upper(), "INR")
    dense = _embed_query(req.semantic_query)
    sparse = _bm25_vector(req.semantic_query)

    price = req.price_max
    steps: list[dict[str, Any]] = []
    fallback = FallbackDebug()

    attempts = [
        {
            "price_max": price,
            "use_tags": True,
            "use_category": True,
            "label": "full_filters",
        },
        {
            "price_max": (price * 1.2) if price is not None else None,
            "use_tags": True,
            "use_category": True,
            "label": "relax_price_20pct",
        },
        {
            "price_max": price,
            "use_tags": False,
            "use_category": True,
            "label": "drop_tags",
        },
        {
            "price_max": price,
            "use_tags": False,
            "use_category": False,
            "label": "drop_category",
        },
        {
            "price_max": None,
            "use_tags": False,
            "use_category": False,
            "label": "semantic_only",
        },
    ]
    seen: set[tuple] = set()
    unique_attempts = []
    for a in attempts:
        key = (a["price_max"], a["use_tags"], a["use_category"])
        if key in seen:
            continue
        seen.add(key)
        unique_attempts.append(a)

    hits_payload: list[dict[str, Any]] = []
    hit_debugs: list[HitDebug] = []
    used = unique_attempts[0]
    qfilter = None
    for a in unique_attempts:
        qfilter = _build_filter(
            req,
            country=country.upper(),
            currency=currency,
            price_max=a["price_max"],
            use_tags=a["use_tags"],
            use_category=a["use_category"],
        )
        points = _query(client, collection, dense, sparse, qfilter, max(req.top_k * 2, 16))
        filtered = []
        for p in points:
            payload = p.payload or {}
            if _passes_price(
                payload, country=country.upper(), currency=currency, price_max=a["price_max"]
            ):
                filtered.append(payload)
            if len(filtered) >= req.top_k:
                break
        steps.append({"action": a["label"], "hits": len(filtered)})
        if filtered:
            used = a
            hits_payload = filtered
            hit_debugs = [
                HitDebug(
                    id=payload.get("id", ""),
                    dense_score=None,
                    sparse_score=None,
                    rrf_rank=rank,
                    payload_excerpt={
                        "title": payload.get("title"),
                        "category_path": payload.get("category_path"),
                        "short_pitch": payload.get("short_pitch"),
                        "price_min": payload.get("price_min"),
                    },
                    review_pending=bool(payload.get("review_pending")),
                )
                for rank, payload in enumerate(filtered, start=1)
            ]
            if a["label"] != "full_filters":
                fallback = FallbackDebug(triggered=True, action=a["label"], steps=steps)
            else:
                fallback = FallbackDebug(triggered=False, action=None, steps=steps)
            break
    else:
        fallback = FallbackDebug(triggered=True, action="none_after_ladder", steps=steps)

    qdrant_query = {
        "filter": str(qfilter) if qfilter else None,
        "fusion": "rrf",
        "attempt": used["label"],
        "country": country.upper(),
        "currency": currency,
        "collection": collection,
        "tenant_id": paths.tenant_id,
    }
    latency = (time.perf_counter() - t0) * 1000
    return hits_payload, qdrant_query, fallback, hit_debugs, latency
