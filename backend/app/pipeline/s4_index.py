"""Stage 4 — embed + upsert to Qdrant."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.openai_client import embedding_model, get_embedding_client, openai_key_present
from app.pipeline.io_utils import ensure_data_dirs, load_hash_ledger, save_hash_ledger
from app.pipeline.run_metrics import record_embedding_usage


def product_uuid(product_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"product-rag:{product_id}"))


def get_qdrant() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_url, check_compatibility=False)


def _create_payload_index(client: QdrantClient, name: str, field: str, schema) -> None:
    try:
        client.create_payload_index(collection_name=name, field_name=field, field_schema=schema)
    except Exception:
        pass


def _facet_index_schema(facet_type: str):
    return {
        "string": models.PayloadSchemaType.KEYWORD,
        "float": models.PayloadSchemaType.FLOAT,
        "int": models.PayloadSchemaType.INTEGER,
        "bool": models.PayloadSchemaType.BOOL,
    }.get(facet_type, models.PayloadSchemaType.KEYWORD)


def ensure_collection(client: QdrantClient, name: str) -> None:
    from app.pipeline.s2_normalize import load_vocab

    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config={
                "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
            },
            sparse_vectors_config={
                "bm25": models.SparseVectorParams(),
            },
        )

    for field, schema in [
        ("category_path", models.PayloadSchemaType.KEYWORD),
        ("use_case_tags", models.PayloadSchemaType.KEYWORD),
        ("target_audience", models.PayloadSchemaType.KEYWORD),
        ("status", models.PayloadSchemaType.KEYWORD),
        ("review_pending", models.PayloadSchemaType.BOOL),
        ("kind", models.PayloadSchemaType.KEYWORD),
        ("brand", models.PayloadSchemaType.KEYWORD),
        ("unit", models.PayloadSchemaType.KEYWORD),
        ("offerings[].prices[].country", models.PayloadSchemaType.KEYWORD),
        ("offerings[].prices[].amount", models.PayloadSchemaType.FLOAT),
        ("offerings[].pricing_type", models.PayloadSchemaType.KEYWORD),
        ("offerings[].interval", models.PayloadSchemaType.KEYWORD),
    ]:
        _create_payload_index(client, name, field, schema)

    # Dynamic facet indexes from vocab (filterable keys only)
    try:
        facet_schemas = (load_vocab().get("facet_schemas") or {})
    except Exception:
        facet_schemas = {}
    for _domain, facets in facet_schemas.items():
        for facet in facets or []:
            if not facet.get("filterable", False):
                continue
            key = facet.get("key")
            if not key:
                continue
            field = f"facets_indexed.{key}"
            _create_payload_index(client, name, field, _facet_index_schema(facet.get("type", "string")))


def _flatten_facets(item: dict[str, Any]) -> dict[str, Any]:
    """Flat map for Qdrant filtering: facets_indexed.{key} = value."""
    out: dict[str, Any] = {}
    for f in item.get("facets") or []:
        if not isinstance(f, dict):
            continue
        key = f.get("key")
        if key is None:
            continue
        out[str(key)] = f.get("value")
    return out


def _hash_embed(text: str, dim: int = 1536) -> list[float]:
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
        vec[(h // dim) % dim] += 0.5
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def _has_openai_key() -> bool:
    return openai_key_present()


def _embed(texts: list[str]) -> list[list[float]]:
    if not _has_openai_key():
        print("WARN: OPENAI_API_KEY missing — using hash embeddings")
        return [_hash_embed(t) for t in texts]
    try:
        client = get_embedding_client()
        model = embedding_model()
        resp = client.embeddings.create(model=model, input=texts)
        record_embedding_usage(resp, model=model)
        by_idx = sorted(resp.data, key=lambda d: d.index)
        return [d.embedding for d in by_idx]
    except Exception as e:
        print(f"WARN: embedding API failed ({e}) — using hash embeddings")
        return [_hash_embed(t) for t in texts]


def _bm25_vector(text: str) -> models.SparseVector:
    tokens = [t.lower() for t in text.replace("/", " ").replace("-", " ").split() if len(t) > 1]
    tf: dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0.0) + 1.0
    indices = []
    values = []
    for term, freq in tf.items():
        idx = int(hashlib.md5(term.encode()).hexdigest()[:8], 16) % 1_000_003
        indices.append(idx)
        values.append(freq)
    return models.SparseVector(indices=indices, values=values)


def run(tenant_id: str = "demo", force_all: bool = False) -> dict:
    paths = ensure_data_dirs(tenant_id)
    client = get_qdrant()
    ensure_collection(client, paths.collection)

    ledger = load_hash_ledger(paths)
    files = sorted(paths.canonical.glob("*.json"))
    to_upsert: list[dict[str, Any]] = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") == "retired":
            continue
        pid = data["id"]
        ch = data["content_hash"]
        if not force_all and ledger.get(pid) == ch:
            continue
        to_upsert.append(data)

    upserted = 0
    batch_size = 16
    for i in range(0, len(to_upsert), batch_size):
        batch = to_upsert[i : i + batch_size]
        texts = [b["embedding_text"] for b in batch]
        dense = _embed(texts)
        points = []
        for item, vec in zip(batch, dense):
            payload = {k: v for k, v in item.items()}
            payload["facets_indexed"] = _flatten_facets(item)
            points.append(
                models.PointStruct(
                    id=product_uuid(item["id"]),
                    vector={
                        "dense": vec,
                        "bm25": _bm25_vector(item["embedding_text"]),
                    },
                    payload=payload,
                )
            )
            ledger[item["id"]] = item["content_hash"]
        client.upsert(collection_name=paths.collection, points=points)
        upserted += len(points)

    save_hash_ledger(paths, ledger)

    active = sum(
        1
        for p in files
        if json.loads(p.read_text(encoding="utf-8")).get("status", "active") == "active"
    )
    count = client.count(collection_name=paths.collection, exact=True).count
    return {"upserted": upserted, "canonical_active": active, "qdrant_points": count, "collection": paths.collection}
