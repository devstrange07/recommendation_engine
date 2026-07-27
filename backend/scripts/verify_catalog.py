"""End-to-end verification for tenant catalog ingest and isolation."""

from __future__ import annotations

import shutil
import sys

from app.catalog_service import create_from_form, ingest_text, list_products, validate_text
from app.pipeline.paths import TenantPaths
from app.rag.search import search_products
from app.schemas import CreatePlanRequest, CreatePriceRequest, CreateProductRequest, SearchRequest

TENANT = "t_verify2"


def main() -> int:
    paths = TenantPaths.for_tenant(TENANT)
    if paths.root.exists():
        shutil.rmtree(paths.root)

    req = CreateProductRequest(
        name="Zephyr Unique Widget XYZ",
        description="Exclusive isolation test product for tenant verify2 only.",
        category="Support/Helpdesk",
        plans=[
            CreatePlanRequest(
                name="Basic",
                feature_text="Tickets and inbox",
                prices=[CreatePriceRequest(country="IN", currency="INR", amount=499)],
            )
        ],
    )
    res = create_from_form(TENANT, req)
    pid = res.products[0].product_id
    print("FORM", res.products[0].status, pid)
    if res.products[0].status not in ("indexed", "flagged"):
        print("FAIL: form ingest did not index")
        return 1

    hits, _, _, _, _ = search_products(
        SearchRequest(semantic_query="Zephyr Unique Widget"), country="IN", tenant_id=TENANT
    )
    tenant_ids = [h.get("id") for h in hits[:5]]
    print("tenant hits", tenant_ids)

    hits_demo, _, _, _, _ = search_products(
        SearchRequest(semantic_query="Zephyr Unique Widget"), country="IN", tenant_id="demo"
    )
    demo_ids = [h.get("id") for h in hits_demo[:5]]
    print("demo hits", demo_ids)
    if pid in demo_ids:
        print("FAIL: product leaked to demo catalog")
        return 1
    print("ISOLATED ok")

    messy = (
        '{"name": "Paste Test CRM", "description": "Leads and pipeline", '
        '"plans": [{"name": "Pro", "prices": [{"country": "IN", "currency": "INR", "amount": 999}]}]}'
    )
    val = validate_text(messy, source_name="paste.json")
    print("JSON validate", val.valid, len(val.products))
    if not val.valid:
        print("FAIL: JSON validate")
        return 1

    res2 = ingest_text(TENANT, messy, source_name="paste.json")
    print("JSON ingest", res2.products[-1].status, res2.products[-1].name)

    txt = (
        "Product: CloudDesk Help\n"
        "Description: Helpdesk for small teams.\n"
        "Plan: Starter at 799 INR/month in India."
    )
    res3 = ingest_text(TENANT, txt, source_name="upload.txt")
    print("TXT ingest", res3.products[-1].status, res3.products[-1].name, res3.products[-1].flags)

    count = len(list_products(TENANT))
    print("PRODUCT COUNT", count)
    if count < 3:
        print("FAIL: expected at least 3 products")
        return 1

    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
