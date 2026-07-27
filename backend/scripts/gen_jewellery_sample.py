"""Generate India jewellery sample catalogs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

UPDATED_AT = "2026-07-27T00:00:00+00:00"
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"

ProductTuple = tuple[str, str, str, str, str, int]


def build_catalog(target_total: int) -> list[ProductTuple]:
    gold_target = round(target_total * 0.50)
    diamond_target = round(target_total * 0.30)
    fashion_target = target_total - gold_target - diamond_target

    designs_gold = ["Necklace", "Bangle", "Mangalsutra", "Chain", "Jhumka", "Ring", "Bracelet", "Kada", "Waist Belt"]
    designs_diamond = ["Solitaire Ring", "Stud Earrings", "Pendant", "Tennis Bracelet", "Halo Ring", "Nose Pin", "Drop Earrings"]
    designs_fashion = [
        "Oxidised Earrings", "Kundan Set", "Silver Anklet", "Temple Pendant", "Statement Choker",
        "Charm Bracelet", "Polki Earrings", "Layered Necklace",
    ]
    purities = ["22K", "18K"]
    weights_gold = [6, 8, 12, 16, 20, 24, 28, 35]
    diamond_carat = [0.20, 0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00]
    fashion_weights = [12, 20, 28, 35, 50, 65, 80]
    collections = ["Wedding", "Festive", "Daily Wear", "Heritage", "Modern", "Minimal"]
    finishes = ["Classic Polish", "Matte Finish", "Antique Finish", "High Shine"]

    items: list[ProductTuple] = []
    seen: set[str] = set()

    for design in designs_gold:
        for purity_i, purity in enumerate(purities):
            for weight_i, weight in enumerate(weights_gold):
                for finish_i, finish in enumerate(finishes):
                    collection = collections[(purity_i + weight_i + finish_i) % len(collections)]
                    name = f"{purity} Hallmarked Gold {design} {weight}g ({collection}, {finish})"
                    if name in seen:
                        continue
                    amount = 5500 * weight + purity_i * 18000 + weight_i * 2200 + finish_i * 1800
                    feat = (
                        f"{purity}; {weight}g; BIS hallmarked; {collection.lower()}; "
                        f"{finish.lower()}; handcrafted finish"
                    )
                    desc = (
                        f"Hallmarked {purity} gold {design.lower()} tailored for Indian {collection.lower()} occasions. "
                        "Crafted for bridal and family gifting preferences."
                    )
                    plan = f"Retail - {purity} {weight}g"
                    items.append((name, "Jewellery/Gold", desc, plan, feat, int(amount)))
                    seen.add(name)
                    if len([x for x in items if x[1] == "Jewellery/Gold"]) >= gold_target:
                        break
                if len([x for x in items if x[1] == "Jewellery/Gold"]) >= gold_target:
                    break
            if len([x for x in items if x[1] == "Jewellery/Gold"]) >= gold_target:
                break
        if len([x for x in items if x[1] == "Jewellery/Gold"]) >= gold_target:
            break

    for design in designs_diamond:
        for carat_i, carat in enumerate(diamond_carat):
            for metal_i, metal in enumerate(["18K Rose Gold", "18K White Gold", "Platinum Finish", "Yellow Gold Tone"]):
                for finish_i, finish in enumerate(finishes):
                    collection = collections[(carat_i + metal_i + finish_i + 1) % len(collections)]
                    name = f"{carat:.2f}ct Diamond {design} in {metal} ({collection}, {finish})"
                    if name in seen:
                        continue
                    amount = int(45000 + carat * 220000 + metal_i * 12000 + carat_i * 6000 + finish_i * 2500)
                    feat = (
                        f"{carat:.2f}ct; certified diamond; {metal}; {collection.lower()}; "
                        f"{finish.lower()}; gift-ready box"
                    )
                    desc = (
                        f"Certified diamond {design.lower()} in {metal} with premium finish. "
                        "Popular for engagement, wedding gifting, and festive occasions in India."
                    )
                    plan = f"Retail - {carat:.2f}ct"
                    items.append((name, "Jewellery/Diamond", desc, plan, feat, amount))
                    seen.add(name)
                    if len([x for x in items if x[1] == "Jewellery/Diamond"]) >= diamond_target:
                        break
                if len([x for x in items if x[1] == "Jewellery/Diamond"]) >= diamond_target:
                    break
            if len([x for x in items if x[1] == "Jewellery/Diamond"]) >= diamond_target:
                break
        if len([x for x in items if x[1] == "Jewellery/Diamond"]) >= diamond_target:
            break

    for design in designs_fashion:
        for weight_i, weight in enumerate(fashion_weights):
            for material_i, material in enumerate(
                ["Silver-tone", "Oxidised", "Kundan", "Pearl", "Temple Style", "Polki", "American Diamond", "Enamel"]
            ):
                for finish_i, finish in enumerate(finishes):
                    collection = collections[(weight_i + material_i + finish_i + 2) % len(collections)]
                    name = f"{material} {design} {weight}g ({collection}, {finish})"
                    if name in seen:
                        continue
                    amount = int(799 + weight * 45 + material_i * 180 + weight_i * 90 + finish_i * 70)
                    feat = (
                        f"{material}; {weight}g; anti-tarnish coating; {collection.lower()}; "
                        f"{finish.lower()}; lightweight comfort"
                    )
                    desc = (
                        f"{material} fashion jewellery {design.lower()} for Indian festive and daily styling. "
                        "Designed for affordability and statement looks."
                    )
                    plan = f"Retail - {material}"
                    items.append((name, "Jewellery/Fashion", desc, plan, feat, amount))
                    seen.add(name)
                    if len([x for x in items if x[1] == "Jewellery/Fashion"]) >= fashion_target:
                        break
                if len([x for x in items if x[1] == "Jewellery/Fashion"]) >= fashion_target:
                    break
            if len([x for x in items if x[1] == "Jewellery/Fashion"]) >= fashion_target:
                break
        if len([x for x in items if x[1] == "Jewellery/Fashion"]) >= fashion_target:
            break

    if len(items) != target_total:
        raise ValueError(f"count mismatch: got {len(items)} need {target_total}")
    return items


def _product(idx: int, row: ProductTuple) -> dict:
    name, category, description, plan_name, feature_text, amount = row
    return {
        "id": f"jew_{idx:03d}",
        "name": name,
        "category": category,
        "unit": "piece",
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
    out = SAMPLES_DIR / f"jewellery_india_{target_total}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"products": products}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cats = Counter(p["category"] for p in products)
    print(
        f"Wrote {out}\n"
        f"total={len(products)} gold={cats['Jewellery/Gold']} "
        f"diamond={cats['Jewellery/Diamond']} fashion={cats['Jewellery/Fashion']}"
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate India jewellery sample JSON")
    parser.add_argument("--count", type=int, default=200, choices=[50, 200, 500, 1000])
    args = parser.parse_args()
    write_catalog(args.count)


if __name__ == "__main__":
    main()
