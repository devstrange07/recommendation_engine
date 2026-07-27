"""Generate a deliberately messy synthetic product catalog."""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.pipeline.io_utils import ensure_data_dirs, write_jsonl
from app.schemas import RawPlan, RawPriceList, RawProduct

CATEGORIES = [
    ("Scheduling/Appointments", "scheduling"),
    ("CRM/Sales", "crm"),
    ("Invoicing/Billing", "invoicing"),
    ("Marketing/Email", "marketing"),
    ("Support/Helpdesk", "support"),
]

# Messy category spellings that map roughly to the above
MESSY_CATEGORY = {
    "scheduling": ["Scheduling", "appointments", "Booking Tools", "automations"],
    "crm": ["CRM", "Sales CRM", "crm", "Sales"],
    "invoicing": ["Invoicing", "Billing", "invoices", "Payments"],
    "marketing": ["Marketing", "Email Marketing", "marketing", "Campaigns"],
    "support": ["Support", "Helpdesk", "support desk", "Customer Service"],
}

COUNTRY_MESS = [
    ("india", "inr"),
    ("IN", "INR"),
    ("In", "₹"),
    ("US", "usd"),
    ("usa", "USD"),
    ("United States", "dollar"),
    ("GB", "gbp"),
    ("uk", "GBP"),
]

PRODUCT_SEEDS = {
    "scheduling": [
        ("BookEase", "appointment booking and calendar sync for small teams"),
        ("SalonFlow", "salon appointment and staff scheduling"),
        ("ClinicSlot", "patient appointment booking for clinics"),
        ("MeetGrid", "meeting scheduler with buffer times"),
        ("Appointly Pro", "online booking pages and reminders"),
        ("CalendarHQ", "shared team calendar and booking links"),
        ("ReserveNow", "reservation system for service businesses"),
        ("SlotMaster", "multi-location appointment scheduling"),
        ("HairBook", "hair salon booking and client history"),
        ("SpaSchedule", "spa treatment booking and packages"),
        ("DocTime", "doctor appointment booking"),
        ("FitBook", "fitness class and trainer scheduling"),
        ("ConsultSlot", "consultant booking pages"),
        ("PetAppoint", "pet grooming appointment tool"),
        ("EventSeat", "event and workshop seating bookings"),
        ("ShiftSync", "staff shift and appointment hybrid"),
    ],
    "crm": [
        ("LeadNest", "CRM for tracking leads and deals"),
        ("PipelineAce", "sales pipeline management"),
        ("ContactHive", "contact and account CRM"),
        ("DealBoard", "visual deal board for small sales teams"),
        ("SalesOrbit", "CRM with email sequences"),
        ("ClientVault", "client relationship tracker"),
        ("OppTrack", "opportunity tracking CRM"),
        ("RevenueMap", "revenue pipeline CRM"),
        ("Prospectly", "prospecting and CRM lite"),
        ("AccountPulse", "account management CRM"),
        ("CloseKit", "closing deals CRM toolkit"),
        ("FunnelCRM", "funnel-centric CRM"),
        ("BizRelation", "B2B relationship CRM"),
        ("TinyCRM", "minimal CRM for freelancers"),
        ("GrowthCRM", "growth-focused sales CRM"),
        ("NexusSales", "team sales CRM"),
    ],
    "invoicing": [
        ("InvoiceBee", "invoicing and payment collection"),
        ("BillCraft", "professional invoice generator"),
        ("PaySlip Pro", "billing and receipts for services"),
        ("CashFlow Docs", "invoices and expense tracking"),
        ("QuickBill", "fast invoicing for freelancers"),
        ("LedgerLite", "simple billing and ledger"),
        ("RecurPay", "recurring billing invoices"),
        ("TaxReady Books", "invoicing with tax lines"),
        ("ClientBill", "client billing portal"),
        ("MoneyNote", "invoice and estimate tool"),
        ("FeeForge", "professional fee invoicing"),
        ("ChargeSheet", "time-based billing invoices"),
        ("PayoutDesk", "invoice and payout tracking"),
        ("SumInvoice", "multi-currency invoicing"),
        ("BillWave", "subscription billing invoices"),
        ("ClearBooks", "clean invoicing for agencies"),
    ],
    "marketing": [
        ("MailBurst", "email campaign platform"),
        ("AudienceGlow", "email marketing and segments"),
        ("CampaignNest", "newsletter and drip campaigns"),
        ("PulseMail", "email automation for SMBs"),
        ("ListLift", "list growth and email blasts"),
        ("SendCraft", "drag-drop email campaigns"),
        ("NewsWire Pro", "newsletter publishing"),
        ("EngageMail", "engagement-focused email tool"),
        ("DripPath", "drip campaign automation"),
        ("SegmentSpark", "audience segmentation email"),
        ("BlastHQ", "bulk email campaigns"),
        ("RetainMail", "retention email sequences"),
        ("PromoPost", "promotional email tool"),
        ("OptIn Lab", "signup forms and email"),
        ("LetterLane", "simple newsletter tool"),
        ("MarketPulse Mail", "marketing email analytics"),
    ],
    "support": [
        ("TicketBay", "helpdesk ticketing system"),
        ("HelpOrbit", "customer support inbox"),
        ("DeskFlow", "shared support mailbox"),
        ("ReplyRack", "ticket and reply management"),
        ("AssistHub", "support knowledge and tickets"),
        ("CareDesk", "customer care helpdesk"),
        ("IssueLane", "issue tracking for support"),
        ("ChatSupport Pro", "live chat and tickets"),
        ("ResolveNow", "fast ticket resolution tool"),
        ("InboxCare", "shared customer inbox"),
        ("SupportGrid", "multi-channel support"),
        ("HelpStack", "stacked ticket queues"),
        ("AgentDesk", "agent helpdesk workspace"),
        ("ServiceQueue", "support queue management"),
        ("FixTicket", "simple ticketing for SMBs"),
        ("CustomerLine", "customer support line tool"),
    ],
}

PLAN_NAMES = [("Basic", "one_time"), ("Pro", "monthly"), ("Business", "monthly"), ("Annual Plus", "annual")]


def _messy_price(country_pair: tuple[str, str], amount_inr: float) -> RawPriceList:
    country, currency = country_pair
    cur = currency.lower()
    # Keep demo budgets realistic: INR ~amount, USD ~amount/80, GBP ~amount/100
    if cur in ("inr", "₹"):
        amount = amount_inr
    elif cur in ("usd", "dollar", "$"):
        amount = round(amount_inr / 80, 2)
    elif cur in ("gbp", "£"):
        amount = round(amount_inr / 100, 2)
    else:
        amount = amount_inr
    discount = None
    strategy = None
    if random.random() < 0.3:
        discount = round(amount * random.choice([0.1, 0.15, 0.2]), 2)
        strategy = random.choice(["10% off", "flat seasonal", "early bird", None])
    return RawPriceList(
        name=f"{country}-{currency}",
        country=country,
        currency=currency,
        amount=amount,
        discount=discount,
        discount_strategy=strategy,
    )


def _build_plans(product_id: str, identical_features: bool) -> list[RawPlan]:
    plans = []
    # INR-centric list prices so "under 2000 a month" is exercisable
    base = random.choice([499, 799, 999, 1299, 1499, 1799, 1999, 2499, 2999])
    feature_pool = [
        "Up to 2 users, email support",
        "Unlimited bookings, SMS reminders",
        "API access, priority support",
        "Custom branding, analytics dashboard",
        "Multi-location, role-based access",
    ]
    shared = "Same features as listed on website" if identical_features else None
    picked = random.sample(PLAN_NAMES, k=random.randint(2, 3))
    used_feats = []
    for i, (pname, billing) in enumerate(picked):
        amount = base * (1 + i * 0.5)
        countries = random.sample(COUNTRY_MESS, k=random.randint(2, 4))
        prices = [_messy_price(c, amount) for c in countries]
        if identical_features:
            ft = shared
        else:
            # unique feature text per plan to avoid accidental indistinguishability
            remaining = [f for f in feature_pool if f not in used_feats] or feature_pool
            ft = remaining[i % len(remaining)]
            used_feats.append(ft)
            if random.random() < 0.08:
                ft = None
        plans.append(
            RawPlan(
                id=f"{product_id}_plan_{i}",
                name=pname,
                feature_text=ft,
                price_lists=prices,
                billing_period=billing if random.random() > 0.15 else random.choice(["mo", "monthly", "one time", "yr"]),
            )
        )
    return plans


def generate(n: int = 80, seed: int = 42) -> tuple[list[RawProduct], dict]:
    random.seed(seed)
    products: list[RawProduct] = []
    defects: list[dict] = []

    # Flatten seeds to hit ~n products
    all_seeds: list[tuple[str, str, str]] = []
    for key, items in PRODUCT_SEEDS.items():
        for name, desc in items:
            all_seeds.append((key, name, desc))
    random.shuffle(all_seeds)
    all_seeds = all_seeds[:n]

    html_quota = max(1, int(n * 0.20))
    contradiction_quota = max(1, int(n * 0.10))
    missing_cat_quota = max(1, int(n * 0.10))
    identical_plan_quota = max(1, int(n * 0.08))
    near_dup_quota = 3

    html_ids = set(random.sample(range(n), k=min(html_quota, n)))
    contradiction_ids = set(random.sample(range(n), k=min(contradiction_quota, n)))
    missing_ids = set(random.sample(range(n), k=min(missing_cat_quota, n)))
    identical_ids = set(random.sample(range(n), k=min(identical_plan_quota, n)))

    for idx, (cat_key, name, desc) in enumerate(all_seeds):
        pid = f"prod_{idx + 1}"
        category = random.choice(MESSY_CATEGORY[cat_key])
        description = desc
        unit = random.choice(["seat", "location", "user", None, "workspace"])

        if idx in html_ids:
            description = (
                f"<p><b>BEST IN CLASS!!</b> {desc}</p>"
                f"<ul><li>Amazing ROI</li><li>World-class support</li></ul>"
                f"<p>Limited time offer — act NOW!!!</p>"
            )
            defects.append({"product_id": pid, "defect": "html_fluff", "field": "description"})

        if idx in contradiction_ids:
            name = f"{name} Pro Suite"
            description = (
                f"Entry-level starter tool for beginners only. Basic free tier features. {desc}"
            )
            defects.append({"product_id": pid, "defect": "contradiction", "field": "name_vs_description"})

        if idx in missing_ids:
            category = None
            unit = None
            defects.append({"product_id": pid, "defect": "missing_category", "field": "category"})

        identical = idx in identical_ids
        if identical:
            defects.append({"product_id": pid, "defect": "plans_indistinguishable", "field": "plans"})

        plans = _build_plans(pid, identical_features=identical)
        products.append(
            RawProduct(
                id=pid,
                name=name,
                category=category,
                unit=unit,
                kb_article=f"https://kb.example.com/{pid}" if random.random() > 0.4 else None,
                description=description,
                plans=plans,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    # Near-duplicates
    for i in range(near_dup_quota):
        src = products[i]
        dup_id = f"prod_{n + i + 1}"
        dup = RawProduct(
            id=dup_id,
            name=src.name + " (Legacy)",
            category=src.category,
            unit=src.unit,
            kb_article=None,
            description=src.description + " Legacy edition.",
            plans=src.plans,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        products.append(dup)
        defects.append({"product_id": dup_id, "defect": "suspected_duplicate", "field": "name", "of": src.id})

    manifest = {
        "total_products": len(products),
        "seed": seed,
        "defect_counts": {
            "html_fluff": sum(1 for d in defects if d["defect"] == "html_fluff"),
            "contradiction": sum(1 for d in defects if d["defect"] == "contradiction"),
            "missing_category": sum(1 for d in defects if d["defect"] == "missing_category"),
            "plans_indistinguishable": sum(1 for d in defects if d["defect"] == "plans_indistinguishable"),
            "suspected_duplicate": sum(1 for d in defects if d["defect"] == "suspected_duplicate"),
        },
        "defects": defects,
    }
    return products, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    ensure_data_dirs()
    products, manifest = generate(n=args.n, seed=args.seed)
    from app.pipeline.paths import TenantPaths

    paths = TenantPaths.for_tenant("demo")
    paths.raw.mkdir(parents=True, exist_ok=True)
    out = paths.raw_catalog
    write_jsonl(out, products)
    (paths.raw / "defect_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(products)} products to {out}")
    print(f"Defect counts: {manifest['defect_counts']}")
    # validate
    for p in products:
        RawProduct.model_validate(p.model_dump())
    print("All products validate as RawProduct.")


if __name__ == "__main__":
    main()
