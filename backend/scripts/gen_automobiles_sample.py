"""Generate India automobiles (cars + EV) sample catalogs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

UPDATED_AT = "2026-07-27T00:00:00+00:00"
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"

ProductTuple = tuple[str, str, str, str, str, int]


def build_catalog(target_total: int) -> list[ProductTuple]:
    ice_target = target_total - round(target_total * 0.20)
    ev_target = target_total - ice_target

    brands_ice = [
        ("Maruti Suzuki", ["Swift", "Baleno", "Dzire", "Brezza", "Grand Vitara"], 650000),
        ("Hyundai", ["i20", "Verna", "Creta", "Alcazar", "Venue"], 800000),
        ("Tata", ["Punch", "Nexon", "Harrier", "Safari", "Altroz"], 750000),
        ("Mahindra", ["XUV 3XO", "Scorpio N", "XUV700", "Bolero Neo"], 900000),
        ("Kia", ["Sonet", "Seltos", "Carens"], 850000),
        ("Toyota", ["Glanza", "Urban Cruiser Hyryder", "Innova Crysta"], 850000),
        ("Honda", ["Amaze", "City", "Elevate"], 780000),
        ("Skoda", ["Slavia", "Kushaq"], 1150000),
        ("Volkswagen", ["Virtus", "Taigun"], 1180000),
        ("MG", ["Astor", "Hector"], 1120000),
    ]
    brands_ev = [
        ("Tata", ["Tiago EV", "Punch EV", "Nexon EV", "Curvv EV"], 850000),
        ("MG", ["Comet EV", "ZS EV", "Windsor EV"], 900000),
        ("Mahindra", ["XUV400 EV", "BE 6", "XEV 9e"], 1400000),
        ("BYD", ["Atto 3", "Seal", "e6"], 2800000),
        ("Hyundai", ["Ioniq 5", "Kona Electric"], 2600000),
        ("Kia", ["EV6"], 5900000),
    ]

    trims = ["Base", "S", "V", "VX", "ZX"]
    transmissions = ["Manual", "AMT", "AT", "DCT"]
    colors = ["Arctic White", "Stealth Black", "Titan Grey", "Deep Blue", "Ruby Red"]
    fuels = [("Petrol", 0), ("Diesel", 80000), ("CNG", 50000)]

    items: list[ProductTuple] = []
    seen: set[str] = set()

    for brand, models, base_price in brands_ice:
        for model in models:
            for trim_i, trim in enumerate(trims):
                for color_i, color in enumerate(colors):
                    fuel, fuel_delta = fuels[(trim_i + color_i) % len(fuels)]
                    transmission = transmissions[(trim_i + color_i) % len(transmissions)]
                    name = f"{brand} {model} {trim} {fuel} - {color}"
                    if name in seen:
                        continue
                    amount = base_price + trim_i * 90000 + color_i * 3000 + fuel_delta
                    feat = (
                        f"{fuel}; {transmission}; 5-seater; dual airbags; "
                        f"rear camera; mileage {16 + (trim_i % 6)} kmpl"
                    )
                    desc = (
                        f"{brand} {model} {trim} for Indian buyers. "
                        f"Balanced city commute and highway usability with {fuel} powertrain."
                    )
                    plan = f"Ex-showroom - {trim} {fuel}"
                    items.append((name, "Automobiles/Cars", desc, plan, feat, amount))
                    seen.add(name)
                    if len([i for i in items if i[1] == "Automobiles/Cars"]) >= ice_target:
                        break
                if len([i for i in items if i[1] == "Automobiles/Cars"]) >= ice_target:
                    break
            if len([i for i in items if i[1] == "Automobiles/Cars"]) >= ice_target:
                break
        if len([i for i in items if i[1] == "Automobiles/Cars"]) >= ice_target:
            break

    for brand, models, base_price in brands_ev:
        for model in models:
            for battery_i, battery in enumerate(["30kWh", "40kWh", "50kWh", "60kWh", "77kWh"]):
                for color_i, color in enumerate(colors):
                    range_km = 250 + battery_i * 60 + color_i * 4
                    name = f"{brand} {model} {battery} - {color}"
                    if name in seen:
                        continue
                    amount = base_price + battery_i * 180000 + color_i * 5000
                    feat = (
                        f"Electric; {range_km} km claimed range; fast charging; "
                        f"6 airbags; connected car tech"
                    )
                    desc = (
                        f"{brand} {model} electric vehicle for India with {battery} battery. "
                        "Suitable for urban commute and long weekend drives."
                    )
                    plan = f"Ex-showroom - {battery}"
                    items.append((name, "Automobiles/Electric", desc, plan, feat, amount))
                    seen.add(name)
                    if len([i for i in items if i[1] == "Automobiles/Electric"]) >= ev_target:
                        break
                if len([i for i in items if i[1] == "Automobiles/Electric"]) >= ev_target:
                    break
            if len([i for i in items if i[1] == "Automobiles/Electric"]) >= ev_target:
                break
        if len([i for i in items if i[1] == "Automobiles/Electric"]) >= ev_target:
            break

    if len(items) != target_total:
        raise ValueError(f"count mismatch: got {len(items)} need {target_total}")
    return items


def _product(idx: int, row: ProductTuple) -> dict:
    name, category, description, plan_name, feature_text, amount = row
    return {
        "id": f"auto_{idx:03d}",
        "name": name,
        "category": category,
        "unit": "vehicle",
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
    out = SAMPLES_DIR / f"automobiles_india_{target_total}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"products": products}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cats = Counter(p["category"] for p in products)
    print(f"Wrote {out}")
    print(f"total={len(products)} cars={cats['Automobiles/Cars']} electric={cats['Automobiles/Electric']}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate India automobiles sample JSON")
    parser.add_argument("--count", type=int, default=200, choices=[50, 200, 500, 1000])
    args = parser.parse_args()
    write_catalog(args.count)


if __name__ == "__main__":
    main()
