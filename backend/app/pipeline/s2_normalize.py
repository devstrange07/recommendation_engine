"""Stage 2 — LLM normalization with structured outputs."""

from __future__ import annotations

import json

import yaml

from app.config import get_settings
from app.openai_client import chat_completion_kwargs, chat_model, get_openai
from app.pipeline.io_utils import ensure_data_dirs, write_json
from app.pipeline.paths import TenantPaths
from app.pipeline.review_store import load_overrides, replace_queue
from app.schemas import NormalizationRecord, Normalized, ReviewFlagItem, StagedProduct

NORMALIZATION_SYSTEM = """You are a catalog data engineer. Normalize messy product catalog records into a strict schema.

Rules:
- Use ONLY values from the provided vocabulary for category_path, use_case_tags, and target_audience.
- If category_raw is already one of the allowed category_paths, keep it exactly — do not remap real-estate inventory into unrelated categories.
- clean_description: 2-3 factual sentences. No marketing fluff, no prices, no HTML.
- short_pitch: one factual line about the property (not SaaS-style pitches).
- plan_features: map each plan_id to a list of differentiator feature strings. If plans are indistinguishable, flag plans_indistinguishable.
- Flag don't guess. Flag only filter-affecting ambiguity (cant_categorize, contradiction, missing_required, plans_indistinguishable, ambiguous_attribute, suspected_duplicate).
- confidence: 0-1 reflecting certainty of the normalization.
- Do not invent prices or IDs.
"""


def load_vocab() -> dict:
    settings = get_settings()
    cats = yaml.safe_load((settings.vocab_dir / "categories.yaml").read_text(encoding="utf-8"))
    common = yaml.safe_load((settings.vocab_dir / "common.yaml").read_text(encoding="utf-8"))
    return {
        "category_paths": [c["path"] for c in cats["categories"]],
        "use_case_tags": common["use_case_tags"],
        "target_audience": common["target_audience"],
    }


def _product_payload(staged: StagedProduct, overrides: dict) -> dict:
    return {
        "product_id": staged.id,
        "name": staged.name,
        "category_raw": staged.category_raw,
        "description_text": staged.description_text,
        "unit": staged.unit,
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "feature_text": p.feature_text,
                "billing_period": p.billing_period,
            }
            for p in staged.plans
        ],
        "human_overrides": overrides.get("fields", {}),
    }


def _has_openai_key() -> bool:
    key = get_settings().openai_api_key.strip()
    return bool(key) and key != "sk-your-key-here"


def _normalize_batch(
    batch: list[StagedProduct], vocab: dict, paths: TenantPaths
) -> list[NormalizationRecord]:
    if not _has_openai_key():
        from app.pipeline.heuristic_normalize import normalize_batch

        print("WARN: OPENAI_API_KEY missing — using heuristic normalizer")
        return normalize_batch(batch, vocab)

    client = get_openai()
    payloads = [_product_payload(s, load_overrides(paths, s.id)) for s in batch]
    user = {
        "vocabulary": vocab,
        "products": payloads,
        "instruction": "Return a JSON object with key 'records' — an array of NormalizationRecord, one per product, same order.",
    }

    def _call():
        resp = client.chat.completions.create(
            model=chat_model(),
            messages=[
                {"role": "system", "content": NORMALIZATION_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(user)
                    + '\nRespond with JSON: {"records":[NormalizationRecord,...]}',
                },
            ],
            response_format={"type": "json_object"},
            **chat_completion_kwargs(),
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        records = data.get("records", data if isinstance(data, list) else [])
        return [NormalizationRecord.model_validate(r) for r in records]

    try:
        return _call()
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


def run(tenant_id: str = "demo") -> dict:
    paths = ensure_data_dirs(tenant_id)
    vocab = load_vocab()

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
    batch_size = 5
    for i in range(0, len(to_process), batch_size):
        batch = to_process[i : i + batch_size]
        records = _normalize_batch(batch, vocab, paths)
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

    existing_queue = []
    if paths.review_queue.exists():
        for line in paths.review_queue.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing_queue.append(ReviewFlagItem.model_validate_json(line))
    processed_ids = {s.id for s in to_process}
    kept = [q for q in existing_queue if q.product_id not in processed_ids]
    replace_queue(paths, kept + queue_items)

    return {"normalized": done, "skipped_unchanged": skipped, "flags_queued": flagged}
