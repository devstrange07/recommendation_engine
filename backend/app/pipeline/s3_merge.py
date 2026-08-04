"""Stage 3 — merge staged + normalization + overrides → canonical."""

from __future__ import annotations

from app.pipeline.io_utils import ensure_data_dirs, write_json
from app.pipeline.review_store import load_overrides
from app.schemas import (
    CanonicalProduct,
    Facet,
    KindLiteral,
    NormalizationRecord,
    Offering,
    StagedProduct,
)

CURRENCY_SYMBOL = {"INR": "₹", "USD": "$", "GBP": "£"}

DISPLAY_SUFFIX = {
    ("recurring", "month"): "/mo",
    ("recurring", "year"): "/yr",
    ("recurring", "week"): "/wk",
    ("recurring", "day"): "/day",
    ("one_time", None): "",
    ("usage", None): "/use",
    ("quote", None): "",
}


def embedding_text(c: CanonicalProduct) -> str:
    tags = ", ".join(c.use_case_tags)
    audience = ", ".join(c.target_audience)
    aliases = ", ".join(c.aliases)
    offering_bits = []
    for o in c.offerings:
        feats = "; ".join(o.features)
        pt = o.pricing_type or "unspecified"
        iv = f"/{o.interval}" if o.interval else ""
        meter = f" {o.meter}" if o.meter else ""
        offering_bits.append(f"{o.name} ({pt}{iv}{meter}): {feats}")
    offerings = " | ".join(offering_bits)
    brand_str = f" by {c.brand}." if c.brand else "."
    unit_str = f" Unit: {c.unit}." if c.unit else ""
    facet_bits = [
        f"{f.key}={f.value}" + (f" {f.unit}" if f.unit else "") for f in c.facets
    ]
    facets_str = f" Attributes: {', '.join(facet_bits)}." if facet_bits else ""
    return (
        f"{c.title}{brand_str} Kind: {c.kind}. Category: {c.category_path}.{unit_str} "
        f"{c.clean_description} Pitch: {c.short_pitch}. "
        f"Use cases: {tags}. Audience: {audience}. Aliases: {aliases}."
        f"{facets_str} "
        f"Plans: {offerings}"
    )


def display_cards(c: CanonicalProduct) -> dict[str, str]:
    cards: dict[str, str] = {}
    currencies = set(c.price_min.keys()) | set(c.price_max.keys())
    pricing_type = None
    interval = None
    for o in c.offerings:
        if o.pricing_type:
            pricing_type = o.pricing_type
            interval = o.interval
            break
    suffix = DISPLAY_SUFFIX.get((pricing_type, interval), "")
    if pricing_type == "recurring" and not suffix and interval:
        suffix = f"/{interval}"
    for cur in currencies:
        sym = CURRENCY_SYMBOL.get(cur, cur + " ")
        lo = c.price_min.get(cur)
        if lo is None:
            continue
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
        elif field == "kind":
            n["kind"] = meta["value"]
        elif field == "brand":
            n["brand"] = meta["value"]

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
                pricing_type=plan.pricing_type,
                interval=plan.interval,
                meter=plan.meter,
                prices=plan.prices,
            )
        )

    remaining = [f for f in record.flags if f.field not in overrides.get("fields", {})]
    review_pending = len(remaining) > 0 or (record.confidence < 0.85 and not overrides)

    kind_raw = n.get("kind") or staged.kind or "physical_good"
    kind: KindLiteral = kind_raw  # type: ignore[assignment]
    brand = n.get("brand") or staged.brand
    facets_raw = n.get("facets") or []
    facets = [f if isinstance(f, Facet) else Facet.model_validate(f) for f in facets_raw]

    return CanonicalProduct(
        id=staged.id,
        kind=kind,
        title=staged.name,
        brand=brand,
        unit=staged.unit,
        category_path=n["category_path"],
        clean_description=n["clean_description"],
        short_pitch=n["short_pitch"],
        use_case_tags=n["use_case_tags"],
        target_audience=n["target_audience"],
        aliases=n["aliases"],
        price_min=staged.price_min,
        price_max=staged.price_max,
        offerings=offerings,
        facets=facets,
        content_hash=staged.content_hash,
        review_pending=review_pending,
        schema_version=2,
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
