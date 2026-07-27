"""Generate India chocolates sample catalogs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

UPDATED_AT = "2026-07-27T00:00:00+00:00"
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"

ProductTuple = tuple[str, str, str, str, str, int]


def build_catalog(target_total: int) -> list[ProductTuple]:
    brands = [
        ("Cadbury", ["Dairy Milk", "Bournville", "Silk", "Fuse"], 60),
        ("Nestle", ["KitKat", "Munch", "Milkybar Choo", "Aero"], 30),
        ("Amul", ["Dark Chocolate", "Fruit & Nut", "Almond Bar"], 80),
        ("Ferrero", ["Rocher", "Raffaello", "Collection"], 299),
        ("Lindt", ["Lindor", "Excellence", "Swiss Classic"], 180),
        ("Fabelle", ["Dark Ganache", "Gianduja", "Ruby Cacao"], 250),
        ("Smoor", ["Artisan Truffle", "Single Origin Bar"], 210),
        ("Mason & Co", ["70% Dark", "Sea Salt", "Orange Peel"], 220),
    ]
    formats = [("Bar", 1), ("Box", 6), ("Gift Tin", 12), ("Celebration Pack", 20), ("Family Pack", 30)]
    flavors = ["Classic", "Almond", "Hazelnut", "Fruit & Nut", "Coffee", "Orange Zest", "Sea Salt"]
    sizes = [25, 50, 100, 150, 250, 400, 750, 1000]

    items: list[ProductTuple] = []
    seen: set[str] = set()
    for brand, lines, base_price in brands:
        for line in lines:
            for flavor_i, flavor in enumerate(flavors):
                for size_i, size_g in enumerate(sizes):
                    fmt, fmt_multiplier = formats[(flavor_i + size_i) % len(formats)]
                    name = f"{brand} {line} {flavor} {size_g}g {fmt}"
                    if name in seen:
                        continue
                    amount = int(base_price + size_g * 2.4 + fmt_multiplier * 22 + flavor_i * 8)
                    amount = max(20, min(amount, 5000))
                    feat = f"{flavor}; {size_g}g; {fmt}; vegetarian; India retail pack"
                    desc = (
                        f"{brand} {line} {flavor} chocolate crafted for Indian gifting and daily indulgence. "
                        f"Pack size {size_g}g in {fmt.lower()} format."
                    )
                    plan = f"Retail - {fmt} {size_g}g"
                    items.append((name, "Confectionery/Chocolates", desc, plan, feat, amount))
                    seen.add(name)
                    if len(items) >= target_total:
                        return items
    if len(items) < target_total:
        raise ValueError(f"insufficient rows: got {len(items)} need {target_total}")
    return items[:target_total]


def _product(idx: int, row: ProductTuple) -> dict:
    name, category, description, plan_name, feature_text, amount = row
    return {
        "id": f"choc_{idx:03d}",
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
    out = SAMPLES_DIR / f"chocolates_india_{target_total}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"products": products}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cats = Counter(p["category"] for p in products)
    print(f"Wrote {out}")
    print(f"total={len(products)} chocolates={cats['Confectionery/Chocolates']}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate India chocolates sample JSON")
    parser.add_argument("--count", type=int, default=200, choices=[50, 200, 500, 1000])
    args = parser.parse_args()
    write_catalog(args.count)


if __name__ == "__main__":
    main()
