"""Stage 0 — LLM-assisted structuring of messy catalog input."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

from app.openai_client import (
    call_with_forced_tool,
    chat_completion_kwargs,
    chat_key_present,
    chat_model,
    get_chat_client,
    is_deepseek,
)
from app.pipeline.run_metrics import record_chat_usage
from app.schemas import ExtractProductsResponse, RawPlan, RawPriceList, RawProduct

EXTRACT_SYSTEM = """You are a catalog data extractor. Convert messy product catalog text or partial JSON into strict RawProduct records.

Output JSON: {"products": [RawProduct, ...]}

RawProduct schema per item:
- id: generate as "user_<8 hex chars>" if missing
- name: string (required)
- category: string or null
- description: string (required, factual)
- plans: array with at least one plan, each with:
  - id: "plan_1", "plan_2", ...
  - name: string
  - feature_text: string or null
  - billing_period: "monthly" | "annual" | "one_time" or messy text
  - price_lists: [{name, country (IN/US/GB or name), currency, amount}]
- updated_at: ISO timestamp

Rules:
- Extract only what is stated; do not invent prices or plan names.
- If price is missing, omit the product or use amount 0 only if explicitly free.
- Prefer ISO country codes IN, US, GB when possible.
"""

EXTRACT_SYSTEM_TOOL = (
    EXTRACT_SYSTEM
    + """

CRITICAL: You MUST call the `submit_products` tool with the extracted products.
Do NOT put JSON in the message content — only the tool call.
"""
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_product_id() -> str:
    return f"user_{uuid.uuid4().hex[:8]}"


def _heuristic_from_text(text: str) -> list[RawProduct]:
    """Minimal fallback when no API key — single product from plain text."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    name = lines[0][:120] if lines else "Untitled Product"
    desc = " ".join(lines[1:]) if len(lines) > 1 else name
    amount = 999.0
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m:
        amount = float(m.group(1))
    return [
        RawProduct(
            id=_new_product_id(),
            name=name,
            category=None,
            description=desc,
            plans=[
                RawPlan(
                    id="plan_1",
                    name="Standard",
                    feature_text=None,
                    billing_period="monthly",
                    price_lists=[
                        RawPriceList(
                            name="Default",
                            country="IN",
                            currency="INR",
                            amount=amount,
                        )
                    ],
                )
            ],
            updated_at=_now_iso(),
        )
    ]


def _parse_structured(text: str) -> list[RawProduct] | None:
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and "products" in data:
        data = data["products"]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return None
    products = []
    for row in data:
        if "id" not in row or not row["id"]:
            row = {**row, "id": _new_product_id()}
        if "updated_at" not in row:
            row = {**row, "updated_at": _now_iso()}
        products.append(RawProduct.model_validate(row))
    return products


def _finalize_products(rows: list[RawProduct]) -> list[RawProduct]:
    out: list[RawProduct] = []
    for row in rows:
        data = row.model_dump()
        if not data.get("id"):
            data["id"] = _new_product_id()
        if not data.get("updated_at"):
            data["updated_at"] = _now_iso()
        out.append(RawProduct.model_validate(data))
    return out


def _llm_extract_deepseek(text: str, *, source_name: str | None = None) -> list[RawProduct]:
    user = {
        "source": source_name or "paste",
        "content": text[:12000],
        "instruction": "Call submit_products with key products — array of RawProduct.",
    }
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM_TOOL},
        {"role": "user", "content": json.dumps(user)},
    ]

    def validate(data: dict) -> list[RawProduct]:
        parsed = ExtractProductsResponse.model_validate(data)
        return _finalize_products(parsed.products)

    return call_with_forced_tool(
        messages=messages,
        tool_name="submit_products",
        tool_description="Submit the extracted RawProduct array. Required.",
        parameters_model=ExtractProductsResponse,
        validate=validate,
    )


def _llm_extract_openai(text: str, *, source_name: str | None = None) -> list[RawProduct]:
    client = get_chat_client()
    user = {
        "source": source_name or "paste",
        "content": text[:12000],
        "instruction": "Return JSON with key products — array of RawProduct.",
    }

    def _call():
        model = chat_model()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": json.dumps(user)},
            ],
            response_format={"type": "json_object"},
            **chat_completion_kwargs(),
        )
        record_chat_usage(resp, model=model)
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        rows = data.get("products", [])
        out = []
        for row in rows:
            if not row.get("id"):
                row["id"] = _new_product_id()
            if not row.get("updated_at"):
                row["updated_at"] = _now_iso()
            out.append(RawProduct.model_validate(row))
        return out

    try:
        return _call()
    except Exception:
        return _call()


def _llm_extract(text: str, *, source_name: str | None = None) -> list[RawProduct]:
    if not chat_key_present():
        return _heuristic_from_text(text)
    if is_deepseek():
        return _llm_extract_deepseek(text, source_name=source_name)
    return _llm_extract_openai(text, source_name=source_name)


def extract_products(text: str, *, source_name: str | None = None) -> list[RawProduct]:
    """Try strict JSON parse, then LLM extraction."""
    structured = _parse_structured(text)
    if structured is not None:
        return structured
    return _llm_extract(text, source_name=source_name)


def parse_csv_text(text: str) -> list[RawProduct]:
    """Best-effort CSV → products; delegates ambiguous rows to LLM."""
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return extract_products(text, source_name="csv")
    header = [h.strip().lower() for h in lines[0].split(",")]
    products: list[RawProduct] = []
    for line in lines[1:]:
        cols = [c.strip() for c in line.split(",")]
        row = dict(zip(header, cols))
        name = row.get("name") or row.get("title") or row.get("product")
        if not name:
            continue
        desc = row.get("description") or row.get("desc") or name
        amount = float(row.get("price") or row.get("amount") or "0")
        country = (row.get("country") or "IN").upper()[:2]
        currency = (row.get("currency") or "INR").upper()
        products.append(
            RawProduct(
                id=_new_product_id(),
                name=name,
                category=row.get("category"),
                description=desc,
                plans=[
                    RawPlan(
                        id="plan_1",
                        name=row.get("plan") or "Standard",
                        feature_text=row.get("features"),
                        billing_period=row.get("billing_period") or "monthly",
                        price_lists=[
                            RawPriceList(
                                name="Default",
                                country=country,
                                currency=currency,
                                amount=amount,
                            )
                        ],
                    )
                ],
                updated_at=_now_iso(),
            )
        )
    return products if products else extract_products(text, source_name="csv")
