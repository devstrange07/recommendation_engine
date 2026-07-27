"""Stage 1 — deterministic pre-processing."""

from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup

from app.pipeline.io_utils import (
    append_jsonl,
    ensure_data_dirs,
    load_hash_ledger,
    read_jsonl,
    write_json,
)
from app.pipeline.paths import TenantPaths
from app.schemas import RawProduct, StagedPlan, StagedPrice, StagedProduct

COUNTRY_MAP = {
    "india": "IN",
    "in": "IN",
    "us": "US",
    "usa": "US",
    "united states": "US",
    "gb": "GB",
    "uk": "GB",
    "united kingdom": "GB",
}

CURRENCY_MAP = {
    "inr": "INR",
    "₹": "INR",
    "usd": "USD",
    "dollar": "USD",
    "$": "USD",
    "gbp": "GBP",
    "£": "GBP",
}

BILLING_MAP = {
    "one_time": "one_time",
    "one time": "one_time",
    "onetime": "one_time",
    "monthly": "monthly",
    "mo": "monthly",
    "month": "monthly",
    "annual": "annual",
    "yearly": "annual",
    "yr": "annual",
    "year": "annual",
}


def strip_html(text: str) -> str:
    soup = BeautifulSoup(text or "", "lxml")
    cleaned = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", cleaned).strip()


def canon_country(raw: str) -> str | None:
    key = (raw or "").strip().lower()
    if len(key) == 2 and key.isalpha():
        return key.upper()
    return COUNTRY_MAP.get(key)


def canon_currency(raw: str) -> str | None:
    key = (raw or "").strip().lower()
    if key in CURRENCY_MAP:
        return CURRENCY_MAP[key]
    if len(key) == 3 and key.isalpha():
        return key.upper()
    return CURRENCY_MAP.get(key)


def canon_billing(raw: str | None) -> str | None:
    if not raw:
        return None
    return BILLING_MAP.get(raw.strip().lower())


def content_hash(name: str, description: str, category: str | None, plans: list) -> str:
    plan_blob = "|".join(
        f"{p.id}:{p.name}:{p.feature_text or ''}:{p.billing_period or ''}" for p in plans
    )
    blob = f"{name}||{description}||{category or ''}||{plan_blob}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def stage_one(raw: RawProduct, prev_hash: str | None) -> StagedProduct | None:
    prices_ok = True
    staged_plans: list[StagedPlan] = []
    for plan in raw.plans:
        prices: list[StagedPrice] = []
        for pl in plan.price_lists:
            country = canon_country(pl.country)
            currency = canon_currency(pl.currency)
            if not country or not currency:
                prices_ok = False
                continue
            discounted = None
            if pl.discount is not None:
                discounted = max(0.0, float(pl.amount) - float(pl.discount))
            prices.append(
                StagedPrice(
                    country=country,
                    currency=currency,
                    amount=float(pl.amount),
                    discounted_amount=discounted,
                )
            )
        if not prices:
            prices_ok = False
        staged_plans.append(
            StagedPlan(
                id=plan.id,
                name=plan.name,
                feature_text=plan.feature_text,
                billing_period=canon_billing(plan.billing_period),  # type: ignore[arg-type]
                prices=prices,
            )
        )

    if not prices_ok or not staged_plans:
        return None

    desc = strip_html(raw.description)
    price_min: dict[str, float] = {}
    price_max: dict[str, float] = {}
    for plan in staged_plans:
        for p in plan.prices:
            amt = p.discounted_amount if p.discounted_amount is not None else p.amount
            price_min[p.currency] = min(price_min.get(p.currency, amt), amt)
            price_max[p.currency] = max(price_max.get(p.currency, amt), amt)

    ch = content_hash(raw.name, desc, raw.category, staged_plans)
    return StagedProduct(
        id=raw.id,
        name=raw.name,
        category_raw=raw.category,
        description_text=desc,
        unit=raw.unit,
        kb_article=raw.kb_article,
        plans=staged_plans,
        price_min=price_min,
        price_max=price_max,
        content_hash=ch,
        needs_normalization=(prev_hash != ch),
    )


def run(tenant_id: str = "demo") -> dict:
    paths = ensure_data_dirs(tenant_id)
    if not paths.raw_catalog.exists():
        raise FileNotFoundError(f"Missing {paths.raw_catalog}; add products or run generate_synthetic")

    ledger = load_hash_ledger(paths)
    for old in paths.staged.glob("*.json"):
        old.unlink()

    rows = read_jsonl(paths.raw_catalog)
    ok = 0
    dead_n = 0
    needs = 0
    for row in rows:
        raw = RawProduct.model_validate(row)
        staged = stage_one(raw, ledger.get(raw.id))
        if staged is None:
            append_jsonl(paths.dead_letter, {"stage": "s1", "product_id": raw.id, "reason": "invalid_prices"})
            dead_n += 1
            continue
        write_json(paths.staged / f"{staged.id}.json", staged)
        ok += 1
        if staged.needs_normalization:
            needs += 1

    return {"staged": ok, "dead_letter": dead_n, "needs_normalization": needs}
