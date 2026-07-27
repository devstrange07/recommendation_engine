"""Stage 3 — merge staged + normalization + overrides → canonical."""

from __future__ import annotations

from app.pipeline.io_utils import ensure_data_dirs, write_json
from app.pipeline.review_store import load_overrides
from app.schemas import (
    CanonicalProduct,
    NormalizationRecord,
    Offering,
    StagedProduct,
)

CURRENCY_SYMBOL = {"INR": "₹", "USD": "$", "GBP": "£"}


def embedding_text(c: CanonicalProduct) -> str:
    tags = ", ".join(c.use_case_tags)
    audience = ", ".join(c.target_audience)
    aliases = ", ".join(c.aliases)
    offering_bits = []
    for o in c.offerings:
        feats = "; ".join(o.features)
        bp = o.billing_period or "unspecified"
        offering_bits.append(f"{o.name} ({bp}): {feats}")
    offerings = " | ".join(offering_bits)
    return (
        f"{c.title}. Category: {c.category_path}. "
        f"{c.clean_description} Pitch: {c.short_pitch}. "
        f"Use cases: {tags}. Audience: {audience}. Aliases: {aliases}. "
        f"Plans: {offerings}"
    )


def display_cards(c: CanonicalProduct) -> dict[str, str]:
    cards: dict[str, str] = {}
    currencies = set(c.price_min.keys()) | set(c.price_max.keys())
    for cur in currencies:
        sym = CURRENCY_SYMBOL.get(cur, cur + " ")
        lo = c.price_min.get(cur)
        if lo is None:
            continue
        bp = None
        for o in c.offerings:
            if o.billing_period:
                bp = o.billing_period
                break
        suffix = {"monthly": "/mo", "annual": "/yr", "one_time": ""}.get(bp or "", "")
        cards[cur] = f"{sym}{lo:,.0f}{suffix}"
    return cards


def merge_one(staged: StagedProduct, record: NormalizationRecord, paths) -> CanonicalProduct:
    overrides = load_overrides(paths, staged.id)
    n = record.normalized.model_dump()
    for field, meta in overrides.get("fields", {}).items():
        if field in n and not isinstance(n[field], (list, dict)):
            n[field] = meta["value"]
        elif field == "category_path":
            n["category_path"] = meta["value"]
        elif field == "use_case_tags":
            n["use_case_tags"] = [meta["value"]]
        elif field == "target_audience":
            n["target_audience"] = [meta["value"]]

    offerings = []
    for plan in staged.plans:
        feats = n.get("plan_features", {}).get(plan.id) or []
        if not feats and plan.feature_text:
            feats = [plan.feature_text]
        offerings.append(
            Offering(
                id=plan.id,
                name=plan.name,
                features=feats,
                billing_period=plan.billing_period,
                prices=plan.prices,
            )
        )

    remaining = [f for f in record.flags if f.field not in overrides.get("fields", {})]
    review_pending = len(remaining) > 0 or (record.confidence < 0.85 and not overrides)

    return CanonicalProduct(
        id=staged.id,
        title=staged.name,
        brand_or_provider=None,
        category_path=n["category_path"],
        clean_description=n["clean_description"],
        short_pitch=n["short_pitch"],
        use_case_tags=n["use_case_tags"],
        target_audience=n["target_audience"],
        aliases=n["aliases"],
        price_min=staged.price_min,
        price_max=staged.price_max,
        offerings=offerings,
        content_hash=staged.content_hash,
        review_pending=review_pending,
    )


def run(tenant_id: str = "demo") -> dict:
    paths = ensure_data_dirs(tenant_id)
    count = 0
    for path in sorted(paths.staged.glob("*.json")):
        staged = StagedProduct.model_validate_json(path.read_text(encoding="utf-8"))
        npath = paths.normalized / f"{staged.id}.json"
        if not npath.exists():
            continue
        record = NormalizationRecord.model_validate_json(npath.read_text(encoding="utf-8"))
        canonical = merge_one(staged, record, paths)
        payload = canonical.model_dump()
        payload["embedding_text"] = embedding_text(canonical)
        payload["display_card"] = display_cards(canonical)
        write_json(paths.canonical / f"{canonical.id}.json", payload)
        count += 1
    return {"canonical": count}
