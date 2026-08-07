"""Deterministic heuristic normalizer used when OPENAI_API_KEY is unset (local verify)."""

from __future__ import annotations

import re

from app.pipeline.vocab_facets import alias_entries, match_canonical_from_entries
from app.schemas import Facet, Flag, KindLiteral, NormalizationRecord, Normalized, StagedProduct

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
    (
        "Automobiles/Cars",
        ["car", "automobile", "hatchback", "sedan", "suv", "muv", "petrol", "diesel"],
    ),
    (
        "Automobiles/Electric",
        ["ev", "electric", "charging", "range", "battery pack", "hybrid"],
    ),
    (
        "Confectionery/Chocolates",
        ["chocolate", "cocoa", "truffle", "praline", "bar", "gift box"],
    ),
    (
        "Travel/Domestic",
        ["india tour", "domestic tour", "pilgrimage", "honeymoon", "getaway", "holiday"],
    ),
    (
        "Travel/Packages",
        ["package", "itinerary", "group departure", "custom trip", "travel package"],
    ),
    (
        "Jewellery/Gold",
        ["gold jewellery", "22k", "18k", "hallmarked", "bangle", "mangalsutra"],
    ),
    (
        "Jewellery/Diamond",
        ["diamond", "solitaire", "studs", "diamond ring", "pendant"],
    ),
    (
        "Jewellery/Fashion",
        ["fashion jewellery", "imitation", "silver jewellery", "daily wear", "costume"],
    ),
    (
        "Pharmaceuticals/OTC",
        ["otc", "over-the-counter", "pain relief", "cold", "cough", "antacid", "paracetamol"],
    ),
    (
        "Pharmaceuticals/Prescription",
        ["prescription", "antibiotic", "hypertension", "diabetes", "chronic", "rx"],
    ),
    (
        "Pharmaceuticals/Wellness",
        ["supplement", "multivitamin", "protein", "immunity", "ayurveda", "wellness"],
    ),
    (
        "FoodService/Cafes",
        [
            "cafe",
            "coffee shop",
            "bakery cafe",
            "espresso",
            "brunch",
            "pastry",
            "tea house",
        ],
    ),
    (
        "FoodService/QuickService",
        [
            "fast food",
            "qsr",
            "takeaway",
            "cloud kitchen",
            "food truck",
            "counter service",
        ],
    ),
    (
        "FoodService/Restaurants",
        [
            "restaurant",
            "dining",
            "fine dining",
            "multi cuisine",
            "thali",
            "buffet",
            "family restaurant",
            "dhaba",
        ],
    ),
    (
        "Healthcare/Telehealth",
        ["telehealth", "telemedicine", "virtual consult", "online doctor", "remote care"],
    ),
    (
        "Healthcare/Diagnostics",
        ["diagnostics", "lab test", "pathology", "imaging", "radiology", "blood test"],
    ),
    (
        "Healthcare/Hospitals",
        ["hospital", "multi specialty", "inpatient", "emergency", "icu"],
    ),
    (
        "Healthcare/Clinics",
        ["clinic", "outpatient", "polyclinic", "specialty clinic", "consultation"],
    ),
    (
        "Hygiene/Sanitizers",
        ["sanitizer", "disinfectant", "hand rub", "antiseptic spray"],
    ),
    (
        "Hygiene/HomeCleaning",
        ["home cleaning", "floor cleaner", "detergent", "dishwasher", "surface cleaner"],
    ),
    (
        "Hygiene/PersonalCare",
        ["personal care", "soap", "shampoo", "toothpaste", "body wash", "hygiene"],
    ),
    (
        "Finance/Loans",
        ["home loan", "personal loan", "mortgage", "emi", "loan", "credit"],
    ),
    (
        "Finance/Insurance",
        ["insurance", "policy", "premium", "health cover", "term life"],
    ),
    (
        "Finance/Banking",
        ["banking", "savings account", "current account", "debit card", "net banking"],
    ),
    (
        "Finance/Wealth",
        ["wealth", "portfolio", "financial planning", "private banking", "aum"],
    ),
    (
        "Clothing/Apparel",
        ["apparel", "clothing", "shirt", "dress", "ethnic wear", "garment"],
    ),
    (
        "Clothing/Footwear",
        ["footwear", "shoes", "sneakers", "sandals", "boots"],
    ),
    (
        "Clothing/Accessories",
        [
            "fashion accessory",
            "handbag",
            "belt",
            "scarf",
            "wallet",
            "apparel accessory",
        ],
    ),
    (
        "Hardware/Tools",
        ["hand tool", "power tool", "drill", "wrench", "diy tools", "tools"],
    ),
    (
        "Hardware/Building",
        ["building hardware", "fasteners", "hinges", "locks", "construction fittings"],
    ),
    (
        "Hardware/Electrical",
        ["electrical hardware", "switch", "socket", "mcb", "electrical fittings", "wire"],
    ),
    (
        "Trading/Brokerage",
        ["brokerage", "demat", "trading account", "equity broker", "stock broker"],
    ),
    (
        "Trading/MutualFunds",
        ["mutual fund", "sip", "nav", "equity fund", "debt fund"],
    ),
    (
        "Trading/Advisory",
        ["investment advisory", "research tips", "portfolio advice", "stock tips"],
    ),
    (
        "NGO/Fundraising",
        ["fundraising", "donation drive", "crowdfunding", "charity appeal"],
    ),
    (
        "NGO/Programs",
        ["ngo program", "community program", "social impact", "outreach"],
    ),
    (
        "NGO/Volunteer",
        ["volunteering", "volunteer drive", "community service", "volunteer"],
    ),
    (
        "Education/EdTech",
        ["edtech", "online learning", "learning app", "e-learning", "lms"],
    ),
    (
        "Education/Vocational",
        ["vocational", "skill training", "iti", "upskilling", "trade course"],
    ),
    (
        "Education/HigherEd",
        ["higher education", "university", "college", "degree", "campus"],
    ),
    (
        "Education/K12",
        ["k12", "primary school", "secondary school", "cbse", "school"],
    ),
    (
        "Photography/Services",
        [
            "photography service",
            "photo shoot",
            "wedding photography",
            "event photography",
        ],
    ),
    (
        "Photography/Equipment",
        ["camera equipment", "lens", "tripod", "photography gear", "dslr"],
    ),
    (
        "Photography/Studios",
        ["photo studio", "studio rental", "portrait studio", "shoot studio"],
    ),
    (
        "SolarPanels/Accessories",
        ["solar inverter", "solar battery", "mounting structure", "solar accessory"],
    ),
    (
        "SolarPanels/Commercial",
        ["commercial solar", "industrial solar", "solar for business", "solar epc"],
    ),
    (
        "SolarPanels/Residential",
        ["rooftop solar", "residential solar", "home solar panel", "solar for home"],
    ),
    (
        "SolarManufacture/Cells",
        ["solar cell", "photovoltaic cell", "wafer", "pv cell"],
    ),
    (
        "SolarManufacture/Modules",
        ["solar module", "solar panel manufacturing", "pv module", "module line"],
    ),
    (
        "SolarManufacture/Equipment",
        ["solar manufacturing equipment", "laminator", "stringer", "fab equipment"],
    ),
    (
        "Paint/Interior",
        ["interior paint", "interior emulsion", "emulsion", "wall paint"],
    ),
    (
        "Paint/Exterior",
        ["exterior paint", "weather coat", "outdoor paint", "facade paint"],
    ),
    (
        "Paint/Industrial",
        ["industrial paint", "protective coating", "epoxy coating", "industrial coating"],
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
    "Automobiles/Cars": ["family_car", "commute", "road_trip"],
    "Automobiles/Electric": ["commute", "daily_driver", "road_trip"],
    "Confectionery/Chocolates": ["gifting", "festival", "daily_wear"],
    "Travel/Domestic": ["leisure_travel", "pilgrimage", "honeymoon"],
    "Travel/Packages": ["leisure_travel", "honeymoon", "pilgrimage"],
    "Jewellery/Gold": ["bridal", "festival", "daily_wear"],
    "Jewellery/Diamond": ["bridal", "gifting", "festival"],
    "Jewellery/Fashion": ["daily_wear", "gifting", "festival"],
    "Pharmaceuticals/OTC": ["pain_relief", "self_care", "immunity"],
    "Pharmaceuticals/Prescription": ["chronic_care", "self_care", "pain_relief"],
    "Pharmaceuticals/Wellness": ["immunity", "self_care", "chronic_care"],
    "FoodService/Restaurants": ["dine_in", "family_dining", "date_night"],
    "FoodService/Cafes": ["brunch", "work_friendly", "dine_in"],
    "FoodService/QuickService": ["takeaway", "delivery", "dine_in"],
    "Healthcare/Telehealth": ["telehealth", "clinical_care", "self_care"],
    "Healthcare/Diagnostics": ["diagnostics", "clinical_care", "self_care"],
    "Healthcare/Hospitals": ["clinical_care", "diagnostics", "telehealth"],
    "Healthcare/Clinics": ["clinical_care", "diagnostics", "telehealth"],
    "Hygiene/Sanitizers": ["sanitizing", "personal_hygiene", "home_cleaning"],
    "Hygiene/HomeCleaning": ["home_cleaning", "sanitizing", "self_care"],
    "Hygiene/PersonalCare": ["personal_hygiene", "self_care", "sanitizing"],
    "Finance/Loans": ["loan", "investment", "banking"],
    "Finance/Insurance": ["insurance", "self_care", "wealth_management"],
    "Finance/Banking": ["banking", "loan", "wealth_management"],
    "Finance/Wealth": ["wealth_management", "investing", "banking"],
    "Clothing/Apparel": ["everyday_wear", "formal_wear", "festival"],
    "Clothing/Footwear": ["everyday_wear", "formal_wear", "gifting"],
    "Clothing/Accessories": ["everyday_wear", "formal_wear", "gifting"],
    "Hardware/Tools": ["diy", "construction", "electrical_fit"],
    "Hardware/Building": ["construction", "diy", "electrical_fit"],
    "Hardware/Electrical": ["electrical_fit", "construction", "diy"],
    "Trading/Brokerage": ["trading", "investing", "wealth_management"],
    "Trading/MutualFunds": ["investing", "wealth_management", "trading"],
    "Trading/Advisory": ["investing", "trading", "wealth_management"],
    "NGO/Fundraising": ["fundraising", "community_program", "volunteering"],
    "NGO/Programs": ["community_program", "fundraising", "volunteering"],
    "NGO/Volunteer": ["volunteering", "community_program", "fundraising"],
    "Education/K12": ["k12_learning", "upskilling", "higher_ed"],
    "Education/HigherEd": ["higher_ed", "upskilling", "k12_learning"],
    "Education/EdTech": ["upskilling", "k12_learning", "higher_ed"],
    "Education/Vocational": ["upskilling", "k12_learning", "higher_ed"],
    "Photography/Services": ["photo_shoot", "studio_rental", "gifting"],
    "Photography/Equipment": ["photo_shoot", "accessory", "studio_rental"],
    "Photography/Studios": ["studio_rental", "photo_shoot", "gifting"],
    "SolarPanels/Residential": ["solar_install", "investment", "diy"],
    "SolarPanels/Commercial": ["solar_install", "investment", "manufacturing"],
    "SolarPanels/Accessories": ["solar_install", "accessory", "diy"],
    "SolarManufacture/Cells": ["manufacturing", "solar_install", "investment"],
    "SolarManufacture/Modules": ["manufacturing", "solar_install", "investment"],
    "SolarManufacture/Equipment": ["manufacturing", "solar_install", "diy"],
    "Paint/Interior": ["interior_paint", "diy", "construction"],
    "Paint/Exterior": ["exterior_paint", "diy", "construction"],
    "Paint/Industrial": ["industrial_coating", "construction", "manufacturing"],
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
    "Automobiles/Cars": ["family", "consumer"],
    "Automobiles/Electric": ["consumer", "family"],
    "Confectionery/Chocolates": ["gift_buyer", "consumer"],
    "Travel/Domestic": ["traveler", "family", "pilgrim"],
    "Travel/Packages": ["traveler", "honeymooner", "family"],
    "Jewellery/Gold": ["bridal_buyer", "family", "consumer"],
    "Jewellery/Diamond": ["bridal_buyer", "gift_buyer", "consumer"],
    "Jewellery/Fashion": ["fashion_buyer", "consumer", "gift_buyer"],
    "Pharmaceuticals/OTC": ["patient", "pharmacy_buyer", "caregiver"],
    "Pharmaceuticals/Prescription": ["patient", "caregiver", "pharmacy_buyer"],
    "Pharmaceuticals/Wellness": ["consumer", "patient", "pharmacy_buyer"],
    "FoodService/Restaurants": ["diner", "family_diner", "couple"],
    "FoodService/Cafes": ["office_crowd", "foodie", "diner"],
    "FoodService/QuickService": ["diner", "office_crowd", "tourist_diner"],
    "Healthcare/Telehealth": ["patient_visitor", "clinic_admin", "caregiver"],
    "Healthcare/Diagnostics": ["patient_visitor", "clinic_admin", "caregiver"],
    "Healthcare/Hospitals": ["patient_visitor", "clinic_admin", "caregiver"],
    "Healthcare/Clinics": ["patient_visitor", "clinic_admin", "caregiver"],
    "Hygiene/Sanitizers": ["household", "consumer", "shopper"],
    "Hygiene/HomeCleaning": ["household", "shopper", "consumer"],
    "Hygiene/PersonalCare": ["household", "consumer", "shopper"],
    "Finance/Loans": ["borrower", "homeowner", "investor"],
    "Finance/Insurance": ["policyholder", "borrower", "household"],
    "Finance/Banking": ["borrower", "household", "investor"],
    "Finance/Wealth": ["investor", "investor_trader", "homeowner"],
    "Clothing/Apparel": ["shopper", "fashion_buyer", "consumer"],
    "Clothing/Footwear": ["shopper", "fashion_buyer", "consumer"],
    "Clothing/Accessories": ["shopper", "fashion_buyer", "gift_buyer"],
    "Hardware/Tools": ["contractor", "homeowner", "consumer"],
    "Hardware/Building": ["contractor", "homeowner", "consumer"],
    "Hardware/Electrical": ["contractor", "homeowner", "consumer"],
    "Trading/Brokerage": ["investor_trader", "investor", "consumer"],
    "Trading/MutualFunds": ["investor_trader", "investor", "household"],
    "Trading/Advisory": ["investor_trader", "investor", "consumer"],
    "NGO/Fundraising": ["donor", "student", "parent"],
    "NGO/Programs": ["donor", "student", "parent"],
    "NGO/Volunteer": ["donor", "student", "parent"],
    "Education/K12": ["student", "parent", "consumer"],
    "Education/HigherEd": ["student", "parent", "consumer"],
    "Education/EdTech": ["student", "parent", "consumer"],
    "Education/Vocational": ["student", "parent", "consumer"],
    "Photography/Services": ["photographer", "consumer", "couple"],
    "Photography/Equipment": ["photographer", "creator", "consumer"],
    "Photography/Studios": ["photographer", "creator", "couple"],
    "SolarPanels/Residential": ["homeowner", "epc_buyer", "investor"],
    "SolarPanels/Commercial": ["epc_buyer", "manufacturer", "investor"],
    "SolarPanels/Accessories": ["homeowner", "epc_buyer", "contractor"],
    "SolarManufacture/Cells": ["manufacturer", "epc_buyer", "investor"],
    "SolarManufacture/Modules": ["manufacturer", "epc_buyer", "investor"],
    "SolarManufacture/Equipment": ["manufacturer", "epc_buyer", "contractor"],
    "Paint/Interior": ["painter", "homeowner", "contractor"],
    "Paint/Exterior": ["painter", "homeowner", "contractor"],
    "Paint/Industrial": ["painter", "manufacturer", "contractor"],
}

# Pitch suffix by top-level category (avoid SaaS-style "crm for teams")
PITCH_BY_TOP = {
    "Residential": "residential listing",
    "Commercial": "commercial listing",
    "Electronics": "device",
    "Automobiles": "vehicle",
    "Confectionery": "chocolate product",
    "Travel": "travel package",
    "Jewellery": "jewellery item",
    "Pharmaceuticals": "pharmaceutical product",
    "FoodService": "restaurant listing",
    "Healthcare": "healthcare offering",
    "Hygiene": "hygiene product",
    "Finance": "finance product",
    "Clothing": "clothing item",
    "Hardware": "hardware product",
    "Trading": "trading product",
    "NGO": "NGO program",
    "Education": "education offering",
    "Photography": "photography offering",
    "SolarPanels": "solar panel offering",
    "SolarManufacture": "solar manufacturing product",
    "Paint": "paint product",
}

KIND_BY_ROOT: dict[str, KindLiteral] = {
    "Electronics": "physical_good",
    "Automobiles": "physical_good",
    "Jewellery": "physical_good",
    "Confectionery": "physical_good",
    "Pharmaceuticals": "physical_good",
    "Clothing": "physical_good",
    "Hardware": "physical_good",
    "Paint": "physical_good",
    "Hygiene": "physical_good",
    "SolarPanels": "physical_good",
    "SolarManufacture": "physical_good",
    "Residential": "physical_good",
    "Commercial": "physical_good",
    "Travel": "experience",
    "FoodService": "venue_offering",
    "Healthcare": "service",
    "Finance": "financial_product",
    "Education": "service",
    "Photography": "service",
    "NGO": "service",
    "Trading": "financial_product",
}


def _infer_kind(category_path: str, staged: StagedProduct | None = None) -> KindLiteral:
    if staged and staged.kind:
        return staged.kind  # type: ignore[return-value]
    root = (category_path or "").split("/")[0]
    return KIND_BY_ROOT.get(root, "physical_good")


def _extract_brand(staged: StagedProduct) -> str | None:
    if staged.brand:
        return staged.brand
    name = (staged.name or "").strip()
    if not name:
        return None
    # Common retail pattern: "Brand Product …"
    first = name.split()[0]
    if first and first[:1].isupper() and len(first) > 1:
        return first
    return None


def _allowed_facet_keys(vocab: dict, category_path: str) -> set[str]:
    root = (category_path or "").split("/")[0]
    schemas = vocab.get("facet_schemas") or {}
    facets = schemas.get(root) or []
    return {str(f.get("key")) for f in facets if f.get("key")}


def _extract_facets(staged: StagedProduct, category_path: str, vocab: dict) -> list[Facet]:
    """Best-effort facet extraction from name + feature_text for offline / fallback normalize."""
    allowed = _allowed_facet_keys(vocab, category_path)
    blob = " ".join(
        [
            staged.name or "",
            staged.description_text or "",
            " ".join(p.feature_text or "" for p in staged.plans),
        ]
    )
    lower = blob.lower()
    found: dict[str, Facet] = {}

    def add(key: str, value: str | float | int, unit: str | None = None) -> None:
        if allowed and key not in allowed:
            return
        if key not in found:
            found[key] = Facet(key=key, value=value, unit=unit)

    # Jewellery
    m = re.search(r"\b(\d{1,2})\s*k\b", lower)
    if m:
        add("purity", f"{m.group(1)}K")
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*g\b", lower)
    if m:
        add("weight_g", float(m.group(1)), "g")
    if "hallmark" in lower or "bis" in lower:
        add("hallmark", "BIS")
    for occasion in ("wedding", "festive", "daily_wear", "gifting"):
        if occasion.replace("_", " ") in lower or occasion in lower:
            add("occasion", occasion)

    # Automobiles — longest alias wins (AMT before AT); short aliases are case-sensitive
    for key in ("fuel", "transmission", "body_type"):
        matched = match_canonical_from_entries(
            blob, alias_entries(vocab, category_path, key)
        )
        if matched:
            add(key, matched)
    m = re.search(r"\b(\d)\s*-?\s*seater\b", lower)
    if m:
        add("seats", int(m.group(1)))

    # Pharma
    for form in ("tablet", "capsule", "syrup", "injection", "cream", "ointment", "drops", "powder", "spray"):
        if re.search(rf"\b{form}\b", lower):
            add("form", form)
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*mg\b", lower)
    if m:
        add("strength", f"{m.group(1)}mg")

    # Travel
    m = re.search(r"\b(\d+)\s*n(?:ights?)?\b", lower)
    if m:
        add("nights", int(m.group(1)))
    for season in ("summer", "winter", "monsoon", "peak", "off_season"):
        if season.replace("_", " ") in lower or season in lower:
            add("season", season)
    for tier in ("budget", "standard", "deluxe", "luxury"):
        if re.search(rf"\b{tier}\b", lower):
            add("hotel_tier", tier)

    # Electronics
    m = re.search(r"\b(\d+)\s*gb\b", lower)
    if m:
        # Ambiguous RAM vs storage — prefer storage for larger values
        gb = int(m.group(1))
        if gb >= 64:
            add("storage_gb", gb)
        else:
            add("ram_gb", gb)
    if re.search(r"\b5g\b", lower):
        add("connectivity", "5G")
    elif re.search(r"\b4g\b", lower):
        add("connectivity", "4G")

    # FoodService
    for meal in ("breakfast", "lunch", "dinner", "brunch", "thali", "buffet", "combo"):
        if re.search(rf"\b{meal}\b", lower):
            add("meal_type", meal)
    if "vegetarian" in lower or " veg " in f" {lower} ":
        add("dietary", "vegetarian")
    elif "non-veg" in lower or "non vegetarian" in lower:
        add("dietary", "non_vegetarian")

    return list(found.values())


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
    resolved_category = category if category in paths else (paths[0] if paths else category)
    return NormalizationRecord(
        product_id=staged.id,
        schema_version=2,
        normalized=Normalized(
            clean_description=clean or f"{staged.name} is a product listing.",
            short_pitch=f"{staged.name} — {pitch_suffix}",
            category_path=resolved_category,
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
            kind=_infer_kind(resolved_category, staged),
            brand=_extract_brand(staged),
            facets=_extract_facets(staged, resolved_category, vocab),
        ),
        confidence=confidence,
        flags=flags,
    )


def normalize_batch(batch: list[StagedProduct], vocab: dict) -> list[NormalizationRecord]:
    return [normalize_one(s, vocab) for s in batch]
