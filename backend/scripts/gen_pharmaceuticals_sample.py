"""Generate India pharmaceuticals sample catalogs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

UPDATED_AT = "2026-07-27T00:00:00+00:00"
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"

ProductTuple = tuple[str, str, str, str, str, int]


def build_catalog(target_total: int) -> list[ProductTuple]:
    otc_target = round(target_total * 0.50)
    rx_target = round(target_total * 0.30)
    wellness_target = target_total - otc_target - rx_target

    otc_products = [
        ("Cipla", "Crocin Advance", "pain relief", 35),
        ("GSK", "Calpol", "fever and pain", 40),
        ("Reckitt", "Dettol Antiseptic", "wound care", 95),
        ("P&G", "Vicks VapoRub", "cold congestion", 85),
        ("Abbott", "Brufen", "pain and inflammation", 55),
        ("Dr Reddy's", "Omez Instant", "acidity", 45),
        ("Sun Pharma", "Volini Gel", "muscle pain", 120),
        ("Himalaya", "Koflet", "cough relief", 75),
        ("Dabur", "Honitus", "cough and throat", 80),
        ("Pfizer", "Gelusil", "antacid", 50),
        ("Bayer", "Saridon", "headache", 30),
        ("Johnson & Johnson", "Benadryl", "cough and allergy", 110),
    ]
    rx_products = [
        ("Cipla", "Asthalin", "respiratory care", 45),
        ("Sun Pharma", "Telma", "hypertension", 95),
        ("Dr Reddy's", "Omez", "acid reflux", 70),
        ("Lupin", "Gluconorm", "diabetes", 130),
        ("Abbott", "Thyronorm", "thyroid", 110),
        ("Torrent", "Azithral", "antibiotic", 140),
        ("Alkem", "Taxim-O", "antibiotic", 160),
        ("Mankind", "Unwanted 72", "emergency contraceptive", 110),
        ("USV", "Glycomet", "diabetes", 85),
        ("Intas", "Atorva", "cholesterol", 120),
        ("Zydus", "Amlodac", "hypertension", 55),
        ("Ipca", "Zerodol", "pain management", 90),
    ]
    wellness_products = [
        ("Himalaya", "Ashwagandha", "stress and immunity", 220),
        ("Dabur", "Chyawanprash", "immunity tonic", 280),
        ("Amway", "Nutrilite Daily", "multivitamin", 1200),
        ("Abbott", "Ensure", "nutrition supplement", 650),
        ("Nestle", "Resource High Protein", "protein nutrition", 780),
        ("Himalaya", "Liv.52", "liver wellness", 150),
        ("Patanjali", "Giloy Ghanvati", "immunity", 120),
        ("HealthKart", "HK Vitals Multivitamin", "daily vitamins", 499),
        ("Fast&Up", "Charge", "electrolyte wellness", 350),
        ("Oziva", "Plant Protein", "protein supplement", 1499),
        ("Kapiva", "Aloe Vera Juice", "digestive wellness", 299),
        ("Organic India", "Tulsi Tea", "immunity herbal", 250),
    ]

    forms = ["Tablet", "Capsule", "Syrup", "Gel", "Ointment", "Suspension", "Drop"]
    strengths = ["5mg", "10mg", "20mg", "50mg", "100mg", "250mg", "500mg", "1000mg"]
    packs = ["10s strip", "15s strip", "30s bottle", "60s bottle", "100ml bottle", "200ml bottle"]
    variants = ["Standard", "Forte", "Plus", "DS", "Kid", "Senior"]

    items: list[ProductTuple] = []
    seen: set[str] = set()

    def add_rows(
        seeds: list[tuple[str, str, str, int]],
        category: str,
        target: int,
        price_cap: int,
    ) -> None:
        nonlocal items
        for brand, product, indication, base_price in seeds:
            for form_i, form in enumerate(forms):
                for strength_i, strength in enumerate(strengths):
                    for pack_i, pack in enumerate(packs):
                        for var_i, variant in enumerate(variants):
                            name = f"{brand} {product} {variant} {strength} {form} ({pack})"
                            if name in seen:
                                continue
                            amount = int(
                                base_price
                                + form_i * 12
                                + strength_i * 18
                                + pack_i * 25
                                + var_i * 15
                            )
                            amount = max(20, min(amount, price_cap))
                            feat = (
                                f"{form}; {strength}; {pack}; {indication}; "
                                "store below 30C; India retail pack"
                            )
                            desc = (
                                f"{brand} {product} {variant} for Indian pharmacy retail. "
                                f"Indicated for {indication}; available as {form.lower()} "
                                f"in {strength} {pack}."
                            )
                            plan = f"Retail - {form} {pack}"
                            items.append((name, category, desc, plan, feat, amount))
                            seen.add(name)
                            if len([x for x in items if x[1] == category]) >= target:
                                return

    add_rows(otc_products, "Pharmaceuticals/OTC", otc_target, 800)
    add_rows(rx_products, "Pharmaceuticals/Prescription", rx_target, 1500)
    add_rows(wellness_products, "Pharmaceuticals/Wellness", wellness_target, 2500)

    if len(items) != target_total:
        raise ValueError(f"count mismatch: got {len(items)} need {target_total}")
    return items


def _product(idx: int, row: ProductTuple) -> dict:
    name, category, description, plan_name, feature_text, amount = row
    return {
        "id": f"pharma_{idx:03d}",
        "name": name,
        "category": category,
        "unit": "pack",
        "kb_article": None,
        "description": description,
        "plans": [
            {
                "id": "plan_1",
                "name": plan_name,
                "feature_text": feature_text,
                "billing_period": "one_time",
                "price_lists": [{"name": "IN-inr", "country": "IN", "currency": "INR", "amount": amount}],
            }
        ],
        "updated_at": UPDATED_AT,
    }


def write_catalog(target_total: int) -> Path:
    products = [_product(i + 1, row) for i, row in enumerate(build_catalog(target_total))]
    assert len(products) == target_total
    assert len({p["name"] for p in products}) == target_total
    out = SAMPLES_DIR / f"pharmaceuticals_india_{target_total}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"products": products}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cats = Counter(p["category"] for p in products)
    print(
        f"Wrote {out}\n"
        f"total={len(products)} otc={cats['Pharmaceuticals/OTC']} "
        f"rx={cats['Pharmaceuticals/Prescription']} wellness={cats['Pharmaceuticals/Wellness']}"
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate India pharmaceuticals sample JSON")
    parser.add_argument("--count", type=int, default=200, choices=[50, 200, 500, 1000])
    args = parser.parse_args()
    write_catalog(args.count)


if __name__ == "__main__":
    main()
