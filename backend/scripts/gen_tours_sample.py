"""Generate India tours and travels sample catalogs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

UPDATED_AT = "2026-07-27T00:00:00+00:00"
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"

ProductTuple = tuple[str, str, str, str, str, int]


def build_catalog(target_total: int) -> list[ProductTuple]:
    domestic_target = target_total - round(target_total * 0.45)
    package_target = target_total - domestic_target

    domestic_destinations = [
        "Goa", "Kerala", "Rajasthan", "Ladakh", "Kashmir", "Himachal", "Andaman",
        "Sikkim", "Meghalaya", "Coorg", "Ooty", "Rann of Kutch", "Varanasi", "Udaipur",
    ]
    package_routes = [
        "Golden Triangle", "Char Dham", "South Temple Circuit", "Northeast Explorer",
        "Kashmir Deluxe", "Kerala Backwaters", "Rajasthan Heritage", "Leh-Nubra-Pangong",
    ]
    durations = [3, 4, 5, 6, 7, 8, 10, 12]
    tiers = [("Standard", 1.0), ("Comfort", 1.25), ("Premium", 1.7), ("Luxury", 2.3)]
    departures = ["Delhi", "Mumbai", "Bengaluru", "Ahmedabad"]
    themes = ["Family", "Honeymoon", "Pilgrimage", "Adventure", "Leisure"]
    seasons = ["Summer", "Monsoon", "Winter", "Festive"]

    items: list[ProductTuple] = []
    seen: set[str] = set()

    for destination in domestic_destinations:
        for nights in durations:
            for dep_i, departure in enumerate(departures):
                for season_i, season in enumerate(seasons):
                    theme = themes[(nights + dep_i + season_i) % len(themes)]
                    tier_name, mult = tiers[(nights + dep_i + season_i) % len(tiers)]
                    name = f"{destination} {nights}N {theme} Tour from {departure} ({tier_name}, {season})"
                    if name in seen:
                        continue
                    amount = int((6000 + nights * 2200 + dep_i * 1500 + season_i * 900) * mult)
                    feat = f"{nights} nights; hotel {tier_name.lower()}; breakfast; transfers; guided sightseeing"
                    desc = (
                        f"India domestic holiday package to {destination} for {theme.lower()} travelers. "
                        f"Departure from {departure} with curated experiences."
                    )
                    plan = f"Package - {nights}N {tier_name}"
                    items.append((name, "Travel/Domestic", desc, plan, feat, amount))
                    seen.add(name)
                    if len([x for x in items if x[1] == "Travel/Domestic"]) >= domestic_target:
                        break
                if len([x for x in items if x[1] == "Travel/Domestic"]) >= domestic_target:
                    break
            if len([x for x in items if x[1] == "Travel/Domestic"]) >= domestic_target:
                break
        if len([x for x in items if x[1] == "Travel/Domestic"]) >= domestic_target:
            break

    for route in package_routes:
        for nights in durations:
            for dep_i, departure in enumerate(departures):
                for season_i, season in enumerate(seasons):
                    tier_name, mult = tiers[(dep_i + nights + season_i + 1) % len(tiers)]
                    theme = themes[(dep_i + nights + season_i + 2) % len(themes)]
                    name = f"{route} {nights}N {tier_name} Group Package from {departure} ({theme}, {season})"
                    if name in seen:
                        continue
                    amount = int((9000 + nights * 2800 + dep_i * 2000 + season_i * 1200) * mult)
                    feat = (
                        f"{nights} nights; {tier_name.lower()} stays; airport/rail transfers; "
                        "some meals included; itinerary support"
                    )
                    desc = (
                        f"India-centric multi-stop travel package covering {route}. "
                        f"Designed for {theme.lower()} travelers with fixed departures from {departure}."
                    )
                    plan = f"Group Departure - {nights}N {tier_name}"
                    items.append((name, "Travel/Packages", desc, plan, feat, amount))
                    seen.add(name)
                    if len([x for x in items if x[1] == "Travel/Packages"]) >= package_target:
                        break
                if len([x for x in items if x[1] == "Travel/Packages"]) >= package_target:
                    break
            if len([x for x in items if x[1] == "Travel/Packages"]) >= package_target:
                break
        if len([x for x in items if x[1] == "Travel/Packages"]) >= package_target:
            break

    if len(items) != target_total:
        raise ValueError(f"count mismatch: got {len(items)} need {target_total}")
    return items


def _product(idx: int, row: ProductTuple) -> dict:
    name, category, description, plan_name, feature_text, amount = row
    return {
        "id": f"tour_{idx:03d}",
        "name": name,
        "category": category,
        "unit": "package",
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
    out = SAMPLES_DIR / f"tours_india_{target_total}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"products": products}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cats = Counter(p["category"] for p in products)
    print(f"Wrote {out}")
    print(f"total={len(products)} domestic={cats['Travel/Domestic']} packages={cats['Travel/Packages']}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate India tours sample JSON")
    parser.add_argument("--count", type=int, default=200, choices=[50, 200, 500, 1000])
    args = parser.parse_args()
    write_catalog(args.count)


if __name__ == "__main__":
    main()
