"""Stage 2 — LLM normalization with structured outputs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
import json

import yaml

from app.config import Settings, get_settings
from app.openai_client import (
    call_with_forced_tool,
    chat_completion_kwargs,
    chat_key_present,
    chat_model,
    get_chat_client,
    is_deepseek,
    retry_on_rate_limit,
)
from app.pipeline.io_utils import ensure_data_dirs, write_json
from app.pipeline.paths import TenantPaths
from app.pipeline.progress import ProgressCallback, emit
from app.pipeline.review_store import load_overrides, replace_queue
from app.schemas import (
    Facet,
    NormalizationBatchResponse,
    NormalizationRecord,
    NormalizationRecordLLM,
    Normalized,
    ReviewFlagItem,
    StagedProduct,
)

_NORMALIZED_FIELD_NAMES = set(Normalized.model_fields.keys())

_NORMALIZATION_RULES = """You are a catalog data engineer. Normalize messy product catalog records into a strict schema.

Rules:
- Use ONLY values from the provided vocabulary for category_path, use_case_tags, and target_audience.
- If category_raw is already one of the allowed category_paths, keep it exactly — do not remap inventory into unrelated categories.
- clean_description: 2-3 factual sentences. No marketing fluff, no prices, no HTML.
- short_pitch: one factual line about the product (not marketing fluff).
- plan_features: array of {plan_id, features[]} differentiators. If plans are indistinguishable, flag plans_indistinguishable.
- kind: infer from category and description. One of: physical_good, digital_good, service, subscription, bundle, experience, venue_offering, financial_product.
- brand: extract the brand/manufacturer name from the product name or description. Null if unclear.
- facets: extract structured attributes from description and feature_text using ONLY the facet keys defined in facet_schemas for this product's category root (e.g. Jewellery root → jewellery facets). Return as [{key, value, unit?}]. Do not invent keys not in the vocabulary. Leave empty if no facets match. Coerce numeric facet values to strings.
- Flag don't guess. Flag only filter-affecting ambiguity (cant_categorize, contradiction, missing_required, plans_indistinguishable, ambiguous_attribute, suspected_duplicate).
- confidence: 0-1 reflecting certainty of the normalization.
- Do not invent prices or IDs.
- Each record MUST nest semantic fields under "normalized" (never flatten them to the top level).

Example NormalizationRecord:
{
  "product_id": "example_001",
  "schema_version": 2,
  "normalized": {
    "clean_description": "Two factual sentences about the product.",
    "short_pitch": "One factual line.",
    "category_path": "Jewellery/Gold",
    "use_case_tags": ["bridal"],
    "target_audience": ["bridal_buyer"],
    "aliases": ["Example Necklace"],
    "plan_features": [{"plan_id": "default", "features": ["22K", "6g", "BIS hallmarked"]}],
    "kind": "physical_good",
    "brand": "Tanishq",
    "facets": [{"key": "purity", "value": "22K"}, {"key": "weight_g", "value": "6", "unit": "g"}]
  },
  "confidence": 0.9,
  "flags": []
}
"""

NORMALIZATION_SYSTEM = _NORMALIZATION_RULES

NORMALIZATION_SYSTEM_TOOL = (
    _NORMALIZATION_RULES
    + """
CRITICAL: You MUST call the `submit_normalization_batch` tool with the records.
Do NOT put JSON in the message content — only the tool call.
"""
)

def load_vocab() -> dict:
    settings = get_settings()
    cats = yaml.safe_load((settings.vocab_dir / "categories.yaml").read_text(encoding="utf-8"))
    common = yaml.safe_load((settings.vocab_dir / "common.yaml").read_text(encoding="utf-8"))
    facet_schemas: dict = {}
    facets_dir = settings.vocab_dir / "facets"
    if facets_dir.exists():
        for path in sorted(facets_dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            domain = data.get("domain")
            if domain:
                facet_schemas[domain] = data.get("facets") or []
    return {
        "category_paths": [c["path"] for c in cats["categories"]],
        "use_case_tags": common["use_case_tags"],
        "target_audience": common["target_audience"],
        "facet_schemas": facet_schemas,
    }


def _product_payload(staged: StagedProduct, overrides: dict) -> dict:
    return {
        "product_id": staged.id,
        "name": staged.name,
        "category_raw": staged.category_raw,
        "description_text": staged.description_text,
        "unit": staged.unit,
        "brand": staged.brand,
        "kind": staged.kind,
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "feature_text": p.feature_text,
                "pricing_type": p.pricing_type,
                "interval": p.interval,
                "meter": p.meter,
            }
            for p in staged.plans
        ],
        "human_overrides": overrides.get("fields", {}),
    }


def _estimate_tokens(staged: StagedProduct) -> int:
    """Rough token estimate from name + description + plan feature text."""
    parts = [staged.name or "", staged.description_text or ""]
    for p in staged.plans:
        parts.append(p.name or "")
        parts.append(p.feature_text or "")
    return max(1, len(json.dumps(parts, ensure_ascii=False)) // 4)


def _group_key(staged: StagedProduct) -> str:
    return (staged.category_raw or "").strip().lower() or "uncategorized"


def _build_batches(
    to_process: list[StagedProduct],
    settings: Settings,
) -> list[list[StagedProduct]]:
    """Group by category_raw, then greedily pack by token budget + product cap."""
    groups: dict[str, list[StagedProduct]] = {}
    group_order: list[str] = []
    for staged in to_process:
        key = _group_key(staged)
        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(staged)

    max_products = max(1, settings.normalize_batch_max_products)
    token_budget = max(1, settings.normalize_batch_token_budget)
    batches: list[list[StagedProduct]] = []

    for key in group_order:
        current: list[StagedProduct] = []
        current_tokens = 0
        for staged in groups[key]:
            est = _estimate_tokens(staged)
            would_exceed = (
                current
                and (
                    len(current) >= max_products
                    or current_tokens + est > token_budget
                )
            )
            if would_exceed:
                batches.append(current)
                current = []
                current_tokens = 0
            current.append(staged)
            current_tokens += est
        if current:
            batches.append(current)

    return batches


def _has_chat_key() -> bool:
    return chat_key_present()


def _coerce_flat_record(raw: dict) -> dict:
    """Wrap top-level Normalized fields into nested `normalized` when missing."""
    if not isinstance(raw, dict):
        return raw
    if isinstance(raw.get("normalized"), dict):
        return raw
    nested = {k: raw[k] for k in _NORMALIZED_FIELD_NAMES if k in raw}
    if not nested:
        return raw
    out = {k: v for k, v in raw.items() if k not in _NORMALIZED_FIELD_NAMES}
    out["normalized"] = nested
    return out


def _plan_features_to_dict(plan_features: object) -> dict[str, list[str]]:
    if isinstance(plan_features, dict):
        return {str(k): list(v) for k, v in plan_features.items()}
    if isinstance(plan_features, list):
        out: dict[str, list[str]] = {}
        for item in plan_features:
            if isinstance(item, dict):
                pid = str(item.get("plan_id", ""))
                feats = item.get("features", [])
            else:
                pid = str(getattr(item, "plan_id", ""))
                feats = getattr(item, "features", [])
            if pid:
                out[pid] = list(feats)
        return out
    return {}


def _coerce_facet_value(raw: object) -> str | float | int | bool:
    if isinstance(raw, (int, float, bool)):
        return raw
    text = str(raw).strip()
    if not text:
        return text
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _facets_from_llm(facets: object) -> list[Facet]:
    out: list[Facet] = []
    if not isinstance(facets, list):
        return out
    for item in facets:
        if isinstance(item, dict):
            key = str(item.get("key", "")).strip()
            if not key:
                continue
            out.append(
                Facet(
                    key=key,
                    value=_coerce_facet_value(item.get("value", "")),
                    unit=item.get("unit"),
                )
            )
        else:
            key = str(getattr(item, "key", "")).strip()
            if not key:
                continue
            out.append(
                Facet(
                    key=key,
                    value=_coerce_facet_value(getattr(item, "value", "")),
                    unit=getattr(item, "unit", None),
                )
            )
    return out


def _llm_record_to_normalization(rec: NormalizationRecordLLM) -> NormalizationRecord:
    n = rec.normalized
    return NormalizationRecord(
        product_id=rec.product_id,
        schema_version=rec.schema_version,
        normalized=Normalized(
            clean_description=n.clean_description,
            short_pitch=n.short_pitch,
            category_path=n.category_path,
            use_case_tags=n.use_case_tags,
            target_audience=n.target_audience,
            aliases=n.aliases,
            plan_features=_plan_features_to_dict(n.plan_features),
            kind=n.kind,
            brand=n.brand,
            facets=_facets_from_llm(n.facets),
        ),
        confidence=rec.confidence,
        flags=rec.flags,
    )


def _record_from_raw(raw: dict) -> NormalizationRecord:
    coerced = _coerce_flat_record(raw)
    nested = coerced.get("normalized")
    if isinstance(nested, dict):
        nested = {**nested}
        if "plan_features" in nested:
            nested["plan_features"] = _plan_features_to_dict(nested.get("plan_features"))
        if "facets" in nested:
            nested["facets"] = _facets_from_llm(nested.get("facets"))
        coerced = {**coerced, "normalized": nested}
    # Prefer LLM wire model (list plan_features), fall back to internal dict shape
    try:
        return _llm_record_to_normalization(NormalizationRecordLLM.model_validate(coerced))
    except Exception:
        return NormalizationRecord.model_validate(coerced)


def _records_from_parsed(
    parsed: NormalizationBatchResponse | None, content: str | None
) -> list[NormalizationRecord]:
    if parsed is not None:
        return [_llm_record_to_normalization(r) for r in parsed.records]
    data = json.loads(content or "{}")
    if isinstance(data, list):
        records_raw = data
    else:
        records_raw = data.get("records", [])
    return [_record_from_raw(r) for r in records_raw]


def _normalize_batch(
    batch: list[StagedProduct],
    vocab: dict,
    paths: TenantPaths,
    *,
    heartbeat_seconds: float = 4.0,
    on_progress: ProgressCallback = None,
    batch_idx: int = 0,
    batch_total: int = 0,
) -> list[NormalizationRecord]:
    if not _has_chat_key():
        from app.pipeline.heuristic_normalize import normalize_batch

        print("WARN: chat API key missing — using heuristic normalizer")
        return normalize_batch(batch, vocab)

    payloads = [_product_payload(s, load_overrides(paths, s.id)) for s in batch]
    user = {
        "vocabulary": vocab,
        "products": payloads,
        "instruction": (
            "Return a JSON object with key 'records' — an array of NormalizationRecord, "
            "one per product, same order. Each record must include nested 'normalized'."
            if not is_deepseek()
            else (
                "Call submit_normalization_batch with key 'records' — an array of "
                "NormalizationRecord, one per product, same order. Each record must "
                "include nested 'normalized'."
            )
        ),
    }

    def _call_openai():
        client = get_chat_client()
        resp = client.chat.completions.parse(
            model=chat_model(),
            messages=[
                {"role": "system", "content": NORMALIZATION_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(user)
                    + '\nRespond with JSON: {"records":[NormalizationRecord,...]}',
                },
            ],
            response_format=NormalizationBatchResponse,
            **chat_completion_kwargs(),
        )
        message = resp.choices[0].message
        return _records_from_parsed(message.parsed, message.content)

    def _call_deepseek():
        def validate(data: dict) -> list[NormalizationRecord]:
            parsed = NormalizationBatchResponse.model_validate(data)
            return _records_from_parsed(parsed, None)

        return call_with_forced_tool(
            messages=[
                {"role": "system", "content": NORMALIZATION_SYSTEM_TOOL},
                {
                    "role": "user",
                    "content": json.dumps(user)
                    + "\nCall submit_normalization_batch with "
                    '{"records":[NormalizationRecord,...]}',
                },
            ],
            tool_name="submit_normalization_batch",
            tool_description=(
                "Submit the normalization batch. Required. "
                "Arguments must match NormalizationBatchResponse."
            ),
            parameters_model=NormalizationBatchResponse,
            validate=validate,
        )

    _call_once = _call_deepseek if is_deepseek() else _call_openai

    def _call():
        return retry_on_rate_limit(_call_once)

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            elapsed = 0.0
            while True:
                try:
                    return future.result(timeout=heartbeat_seconds)
                except TimeoutError:
                    elapsed += heartbeat_seconds
                    emit(
                        on_progress,
                        type="subtask",
                        phase="normalize",
                        message=(
                            f"Normalize batch {batch_idx}/{batch_total}: "
                            f"still running ({int(elapsed)}s)"
                        ),
                        detail={
                            "batch_index": batch_idx,
                            "batch_total": batch_total,
                            "batch_size": len(batch),
                            "elapsed_seconds": int(elapsed),
                            "heartbeat": True,
                        },
                    )
    except Exception as first_err:
        try:
            return _call()
        except Exception:
            print(f"WARN: LLM normalizer failed ({first_err}) — using heuristic normalizer")
            from app.pipeline.heuristic_normalize import normalize_batch

            return normalize_batch(batch, vocab)


def _apply_overrides(record: NormalizationRecord, overrides: dict) -> NormalizationRecord:
    fields = overrides.get("fields", {})
    n = record.normalized
    data = n.model_dump()
    for field, meta in fields.items():
        if field in data:
            data[field] = meta["value"] if not isinstance(data[field], list) else [meta["value"]]
        if field == "category_path":
            data["category_path"] = meta["value"]
        if field.startswith("plan_features."):
            pid = field.split(".", 1)[1]
            data["plan_features"][pid] = [meta["value"]]
    remaining_flags = [f for f in record.flags if f.field not in fields]
    return NormalizationRecord(
        product_id=record.product_id,
        schema_version=record.schema_version,
        normalized=Normalized.model_validate(data),
        confidence=record.confidence,
        flags=remaining_flags,
    )


def run(
    tenant_id: str = "demo",
    *,
    on_progress: ProgressCallback = None,
) -> dict:
    paths = ensure_data_dirs(tenant_id)
    vocab = load_vocab()
    settings = get_settings()

    to_process: list[StagedProduct] = []
    skipped = 0
    for path in sorted(paths.staged.glob("*.json")):
        staged = StagedProduct.model_validate_json(path.read_text(encoding="utf-8"))
        existing = paths.normalized / f"{staged.id}.json"
        if not staged.needs_normalization and existing.exists():
            skipped += 1
            continue
        to_process.append(staged)

    queue_items: list[ReviewFlagItem] = []
    done = 0
    flagged = 0
    batches = _build_batches(to_process, settings)
    batch_total = len(batches)
    if batch_total == 0:
        emit(
            on_progress,
            type="subtask",
            phase="normalize",
            message="No products need normalization",
            detail={"batch_total": 0, "total_products": 0},
        )

    # Emit dispatch events before workers start so the UI can allocate lines.
    for batch_idx, batch in enumerate(batches, start=1):
        emit(
            on_progress,
            type="subtask",
            phase="normalize",
            message=(
                f"Normalize batch {batch_idx}/{batch_total}: "
                f"sending {len(batch)} product(s)"
            ),
            detail={
                "batch_index": batch_idx,
                "batch_total": batch_total,
                "batch_size": len(batch),
                "processed": done,
                "flagged": flagged,
            },
        )

    def _process_batch(
        batch_idx: int, batch: list[StagedProduct]
    ) -> tuple[int, list[StagedProduct], list[NormalizationRecord]]:
        records = _normalize_batch(
            batch,
            vocab,
            paths,
            on_progress=on_progress,
            batch_idx=batch_idx,
            batch_total=batch_total,
        )
        return batch_idx, batch, records

    workers = max(1, min(settings.normalize_concurrency, batch_total or 1))
    if batches:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_process_batch, idx, batch): idx
                for idx, batch in enumerate(batches, start=1)
            }
            for future in as_completed(futures):
                batch_idx, batch, records = future.result()
                for record in records:
                    overrides = load_overrides(paths, record.product_id)
                    if overrides:
                        record = _apply_overrides(record, overrides)
                    write_json(paths.normalized / f"{record.product_id}.json", record)
                    done += 1
                    name = next((s.name for s in batch if s.id == record.product_id), None)
                    for flag in record.flags:
                        if flag.field in overrides.get("fields", {}):
                            continue
                        flagged += 1
                        queue_items.append(
                            ReviewFlagItem(
                                product_id=record.product_id,
                                product_name=name,
                                flag=flag,
                                recommended=flag.recommended,
                            )
                        )
                emit(
                    on_progress,
                    type="subtask",
                    phase="normalize",
                    message=(
                        f"Normalize batch {batch_idx}/{batch_total}: complete "
                        f"({done}/{len(to_process)} products)"
                    ),
                    detail={
                        "batch_index": batch_idx,
                        "batch_total": batch_total,
                        "processed": done,
                        "total_products": len(to_process),
                        "flagged": flagged,
                    },
                )

    existing_queue = []
    if paths.review_queue.exists():
        for line in paths.review_queue.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing_queue.append(ReviewFlagItem.model_validate_json(line))
    processed_ids = {s.id for s in to_process}
    kept = [q for q in existing_queue if q.product_id not in processed_ids]
    replace_queue(paths, kept + queue_items)

    return {"normalized": done, "skipped_unchanged": skipped, "flags_queued": flagged}
