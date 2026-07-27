"""Deterministic heuristic normalizer used when OPENAI_API_KEY is unset (local verify)."""

from __future__ import annotations

import re

from app.schemas import Flag, NormalizationRecord, Normalized, StagedProduct

CATEGORY_KEYWORDS = [
    (
        "Residential/Apartments",
        ["apartment", "flat", "bhk", "high-rise", "tower", "residential"],
    ),
    (
        "Residential/Bungalows",
        ["bungalow", "villa", "independent house", "row house"],
    ),
    ("Residential/Plots", ["plot", "land parcel", "residential plot"]),
    (
        "Commercial/Offices",
        ["office", "workspace", "floor plate", "business center", "corporate"],
    ),
    (
        "Commercial/Retail",
        ["retail", "shop", "showroom", "high street", "storefront"],
    ),
    (
        "Electronics/Accessories",
        [
            "accessory",
            "earbuds",
            "buds",
            "charger",
            "power bank",
            "screen protector",
            "smartwatch",
            "watch band",
            "cable",
            "magsafe",
            "case",
            "cover",
        ],
    ),
    (
        "Electronics/Smartphones",
        ["smartphone", "phone", "mobile", "galaxy", "android", "iphone", "handset"],
    ),
    (
        "Electronics/Foldables",
        ["foldable", "fold", "flip", "clamshell", "galaxy z"],
    ),
]

USE_CASE_BY_CAT = {
    "Residential/Apartments": ["primary_residence", "sale", "ready_possession"],
    "Residential/Bungalows": ["primary_residence", "sale", "ready_possession"],
    "Residential/Plots": ["investment", "sale"],
    "Commercial/Offices": ["office_use", "sale", "investment"],
    "Commercial/Retail": ["retail_frontage", "sale", "investment"],
    "Electronics/Smartphones": ["daily_driver", "flagship", "camera"],
    "Electronics/Foldables": ["flagship", "compact", "daily_driver"],
    "Electronics/Accessories": ["accessory", "audio", "charging"],
}

AUDIENCE_BY_CAT = {
    "Residential/Apartments": ["end_user_buyer", "family_buyer", "nri_buyer"],
    "Residential/Bungalows": ["family_buyer", "end_user_buyer", "nri_buyer"],
    "Residential/Plots": ["investor", "end_user_buyer"],
    "Commercial/Offices": ["sme_office", "investor"],
    "Commercial/Retail": ["retailer", "investor", "sme_office"],
    "Electronics/Smartphones": ["consumer", "power_user", "creator"],
    "Electronics/Foldables": ["consumer", "power_user", "creator"],
    "Electronics/Accessories": ["consumer", "power_user"],
}

# Pitch suffix by top-level category (avoid SaaS-style "crm for teams")
PITCH_BY_TOP = {
    "Residential": "residential listing",
    "Commercial": "commercial listing",
    "Electronics": "device",
}


def _guess_category(staged: StagedProduct, vocab_paths: list[str]) -> tuple[str, list[Flag]]:
    flags: list[Flag] = []
    raw = (staged.category_raw or "").strip()
    if raw and raw in vocab_paths:
        return raw, flags

    blob = f"{staged.name} {raw} {staged.description_text}".lower()
    best = None
    best_score = 0
    for path, keys in CATEGORY_KEYWORDS:
        if path not in vocab_paths:
            continue
        score = sum(1 for k in keys if k in blob)
        if score > best_score:
            best_score = score
            best = path
    if staged.category_raw is None or (raw and raw not in vocab_paths):
        # Only star a recommendation when keywords actually matched.
        recommended = best if best_score > 0 else None
        provisional = best or (vocab_paths[0] if vocab_paths else "Residential/Apartments")
        flags.append(
            Flag(
                type="cant_categorize",
                field="category_path",
                issue="Missing or unknown raw category; heuristic assigned best guess",
                options=list(vocab_paths),
                recommended=recommended,
            )
        )
        return provisional, flags
    return best or (vocab_paths[0] if vocab_paths else "Residential/Apartments"), flags


def normalize_one(staged: StagedProduct, vocab: dict) -> NormalizationRecord:
    paths = list(vocab.get("category_paths") or [])
    category, flags = _guess_category(staged, paths)
    # plans indistinguishable?
    feat_texts = [p.feature_text for p in staged.plans]
    non_null = [t for t in feat_texts if t]
    if len(feat_texts) >= 2 and non_null and len(set(feat_texts)) == 1:
        flags.append(
            Flag(
                type="plans_indistinguishable",
                field="plans",
                issue="Plan feature_text values are identical",
                options=[p.name for p in staged.plans] + ["differentiate_manually"],
                recommended="differentiate_manually",
            )
        )

    plan_features = {}
    for p in staged.plans:
        if p.feature_text:
            plan_features[p.id] = [x.strip() for x in re.split(r"[,;]", p.feature_text) if x.strip()]
        else:
            plan_features[p.id] = [f"{p.name} tier"]

    # Clean description: strip marketing words
    desc = staged.description_text
    for noise in ["BEST IN CLASS!!", "Amazing ROI", "World-class support", "act NOW!!!", "Limited time offer"]:
        desc = desc.replace(noise, "")
    desc = re.sub(r"\s+", " ", desc).strip()
    sentences = [s.strip() for s in re.split(r"[.!?]", desc) if s.strip()]
    clean = ". ".join(sentences[:3])
    if clean and not clean.endswith("."):
        clean += "."

    top = category.split("/")[0] if category else "Residential"
    pitch_suffix = PITCH_BY_TOP.get(top, "listing")
    confidence = 0.9 if not flags else 0.55
    return NormalizationRecord(
        product_id=staged.id,
        normalized=Normalized(
            clean_description=clean or f"{staged.name} is a property listing.",
            short_pitch=f"{staged.name} — {pitch_suffix}",
            category_path=category if category in paths else (paths[0] if paths else category),
            use_case_tags=[
                t
                for t in USE_CASE_BY_CAT.get(category, vocab["use_case_tags"][:2])
                if t in vocab.get("use_case_tags", [])
            ][:3]
            or vocab["use_case_tags"][:2],
            target_audience=[
                a
                for a in AUDIENCE_BY_CAT.get(category, vocab["target_audience"][:2])
                if a in vocab.get("target_audience", [])
            ][:3]
            or vocab["target_audience"][:2],
            aliases=[staged.name.split()[0]] if staged.name else [],
            plan_features=plan_features,
        ),
        confidence=confidence,
        flags=flags,
    )


def normalize_batch(batch: list[StagedProduct], vocab: dict) -> list[NormalizationRecord]:
    return [normalize_one(s, vocab) for s in batch]
