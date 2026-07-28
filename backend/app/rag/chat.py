"""Chat agent loop with search_products tool via Responses API."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.config import get_settings
from app.openai_client import chat_model, get_openai, responses_kwargs
from app.rag.query_understanding import build_search_products_tool, parse_search_request
from app.rag.search import COUNTRY_CURRENCY, clean_query_for_embedding, search_products
from app.schemas import (
    ChatRequest,
    ChatResponse,
    DebugTrace,
    ProductCard,
    SearchRequest,
)

CHAT_SYSTEM = """You are a helpful sales assistant for this product catalog.

Rules:
- You MUST call search_products before recommending any products.
- Gather requirements conversationally (budget, category, features, use case). If results would be too broad (>12 hits conceptually) or intent is vague, ask exactly ONE narrowing question — do not dump a long list.
- Pitch at most 3 products. Reference them by [ID] matching the injected cards (e.g. [prod_015]).
- Never invent prices. Quote prices ONLY from the injected product cards for the user's country.
- If a fallback was triggered (relaxed filters), say so honestly ("nothing under ₹X, closest is…").
- If the user is making small talk with no product intent, reply briefly without searching.
- Stay within this catalog's domain as described in CATALOG CONTEXT. Do not assume a different vertical.
- When the user excludes something ("not X", "no X", "except X", "without X", "other than X"), pass X via search_products exclude_terms and remove X plus the negation phrase from semantic_query.
"""


def build_catalog_context(tenant_id: str, catalog_title: str | None = None) -> str:
    """Sample titles/categories from canonical products so the model knows the catalog domain."""
    from app.pipeline.io_utils import ensure_data_dirs

    paths = ensure_data_dirs(tenant_id)
    categories: list[str] = []
    titles: list[str] = []
    seen_cats: set[str] = set()

    files = sorted(paths.canonical.glob("*.json"))[:12]
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        cat = data.get("category_path")
        if cat and cat not in seen_cats and len(categories) < 8:
            seen_cats.add(cat)
            categories.append(cat)
        title = data.get("title")
        if title and len(titles) < 6:
            titles.append(title)

    name = (catalog_title or "").strip() or tenant_id
    lines = ["CATALOG CONTEXT:", f"- Catalog name: {name}"]
    if categories:
        lines.append(f"- Categories in this catalog: {', '.join(categories)}")
    if titles:
        lines.append(f"- Example products: {'; '.join(titles)}")
    if not categories and not titles:
        lines.append("- No products indexed yet in this catalog.")
    lines.append(
        "Stay within this catalog's domain. Do not assume real-estate or any other vertical."
    )
    return "\n".join(lines)


def _system_prompt(body: ChatRequest, tenant_id: str) -> str:
    return (
        CHAT_SYSTEM
        + "\n"
        + build_catalog_context(tenant_id, body.catalog_title)
        + f"\nUser country for this session: {body.country}. Currency is bound server-side."
    )


def _cards_from_hits(hits: list[dict[str, Any]], country: str) -> list[ProductCard]:
    currency = COUNTRY_CURRENCY.get(country.upper(), "INR")
    cards = []
    for h in hits[:8]:
        display = (h.get("display_card") or {}).get(currency)
        if not display:
            # fallback from price_min
            lo = (h.get("price_min") or {}).get(currency)
            display = f"{lo}" if lo is not None else "price on request"
        cards.append(
            ProductCard(
                id=h["id"],
                title=h.get("title") or h["id"],
                pitch=h.get("short_pitch") or "",
                price_display=display,
                plan_names=[o.get("name", "") for o in h.get("offerings") or []],
            )
        )
    return cards


def _inject_block(hits: list[dict[str, Any]], country: str) -> str:
    currency = COUNTRY_CURRENCY.get(country.upper(), "INR")
    lines = ["PRODUCT CARDS (quote prices only from here):"]
    for h in hits[:8]:
        display = (h.get("display_card") or {}).get(currency, "n/a")
        plans = []
        for o in h.get("offerings") or []:
            feats = ", ".join(o.get("features") or [])
            bp = o.get("billing_period") or ""
            plans.append(f"  - {o.get('name')} ({bp}): {feats}")
        lines.append(
            f"[{h.get('id')}] {h.get('title')} — {h.get('short_pitch')} | {display}\n"
            + "\n".join(plans)
        )
    return "\n".join(lines)


# session memory for previous filters (in-process)
_PREV_FILTERS: dict[str, dict] = {}
_INTENSIFIERS = {"too", "very", "quite", "extremely", "somewhat", "really"}
_NEGATION_RE = re.compile(
    r"\b(?:not|no|nothing|except|excluding|without|other than)\s+(?:from\s+)?"
    r"([A-Za-z0-9][\w&'-]*(?:\s+[A-Za-z0-9][\w&'-]*){0,1})",
    re.IGNORECASE,
)
logger = logging.getLogger(__name__)


def _has_openai_key() -> bool:
    key = get_settings().openai_api_key.strip()
    return bool(key) and key != "sk-your-key-here"


def _usage_total(resp: Any) -> int:
    usage = getattr(resp, "usage", None)
    if not usage:
        return 0
    return int(getattr(usage, "total_tokens", None) or 0)


def _reasoning_tokens(resp: Any) -> int:
    usage = getattr(resp, "usage", None)
    if not usage:
        return 0
    details = getattr(usage, "output_tokens_details", None)
    if details is None:
        return 0
    return int(getattr(details, "reasoning_tokens", None) or 0)


def _reasoning_summary(resp: Any) -> str | None:
    texts: list[str] = []
    for item in getattr(resp, "output", None) or []:
        if getattr(item, "type", None) != "reasoning":
            continue
        for part in getattr(item, "summary", None) or []:
            text = getattr(part, "text", None)
            if text is None and isinstance(part, dict):
                text = part.get("text")
            if text:
                texts.append(str(text))
    if not texts:
        return None
    return "\n\n".join(texts)


def _first_function_call(resp: Any, name: str = "search_products") -> Any | None:
    for item in getattr(resp, "output", None) or []:
        if getattr(item, "type", None) == "function_call" and getattr(item, "name", None) == name:
            return item
    return None


def _conversation_input(body: ChatRequest) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in body.messages]


def _regex_negation_terms(text: str) -> list[str]:
    terms: list[str] = []
    for m in _NEGATION_RE.finditer(text):
        phrase = m.group(1).strip()
        words = phrase.split()
        if words and words[0].lower() in _INTENSIFIERS:
            words = words[1:]
        if not words:
            continue
        phrase = " ".join(words)
        terms.append(phrase)
        if len(words) > 1:
            terms.append(words[0])
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped


def _apply_negation_backstop(req: SearchRequest, body: ChatRequest, debug: DebugTrace | None = None) -> None:
    last_user_msg = next((m.content for m in reversed(body.messages) if m.role == "user"), "")
    if not last_user_msg.strip():
        return
    existing = {t.lower() for t in req.exclude_terms}
    regex_terms = [t for t in _regex_negation_terms(last_user_msg) if t.lower() not in existing]
    if not regex_terms:
        return
    logger.info("regex negation backstop added terms=%s (llm had=%s)", regex_terms, req.exclude_terms)
    req.exclude_terms.extend(regex_terms)
    if debug is not None:
        debug.turn_flow.append(f"exclude_terms_regex_backstop_added:{len(regex_terms)}")


def _heuristic_search_request(body: ChatRequest) -> SearchRequest:
    from app.schemas import SearchRequest

    text = " ".join(m.content for m in body.messages if m.role == "user").lower()
    category = None
    tags: list[str] = []
    audience: list[str] = []
    billing = None
    price_max = None
    if any(
        w in text
        for w in (
            "accessory",
            "accessories",
            "earbuds",
            "buds",
            "charger",
            "power bank",
            "screen protector",
            "smartwatch",
            "watch band",
            "cable",
            "magsafe",
            "phone case",
            "back cover",
        )
    ):
        category = "Electronics/Accessories"
        tags = ["accessory", "audio", "charging"]
        audience = ["consumer", "power_user"]
    elif any(w in text for w in ("foldable", "fold", "flip", "clamshell")):
        category = "Electronics/Foldables"
        tags = ["flagship", "compact", "daily_driver"]
        audience = ["consumer", "power_user", "creator"]
    elif any(
        w in text
        for w in ("smartphone", "phone", "mobile", "galaxy", "android", "iphone", "handset")
    ):
        category = "Electronics/Smartphones"
        tags = ["daily_driver", "flagship", "camera"]
        audience = ["consumer", "power_user", "creator"]
    elif any(w in text for w in ("retail", "shop", "showroom", "storefront")):
        category = "Commercial/Retail"
        tags = ["retail_frontage", "sale"]
        audience = ["retailer", "investor"]
    elif any(w in text for w in ("commercial", "office", "workspace", "business center")):
        category = "Commercial/Offices"
        tags = ["office_use", "sale"]
        audience = ["sme_office", "investor"]
    elif any(w in text for w in ("bungalow", "villa", "independent house")):
        category = "Residential/Bungalows"
        tags = ["primary_residence", "sale"]
        audience = ["family_buyer", "end_user_buyer"]
    elif any(w in text for w in ("plot", "land")):
        category = "Residential/Plots"
        tags = ["investment", "sale"]
        audience = ["investor", "end_user_buyer"]
    elif any(w in text for w in ("apartment", "flat", "bhk", "residential")):
        category = "Residential/Apartments"
        tags = ["primary_residence", "sale"]
        audience = ["end_user_buyer", "family_buyer"]
    if "lease" in text or "rent" in text:
        billing = "monthly"
        if "lease" not in tags:
            tags = [*tags, "lease"] if tags else ["lease"]
    if "sale" in text or "buy" in text or "purchase" in text:
        billing = billing or "one_time"
    import re

    m = re.search(r"under\s+(\d+(?:\.\d+)?)", text) or re.search(r"below\s+(\d+(?:\.\d+)?)", text)
    if m:
        price_max = float(m.group(1))
    return SearchRequest(
        semantic_query=text or "products",
        category_path=category,
        use_case_tags=tags,
        target_audience=audience,
        price_max=price_max,
        billing_period=billing,
    )


def run_chat_turn(body: ChatRequest, tenant_id: str = "demo") -> ChatResponse:
    debug = DebugTrace(turn_flow=["received"])
    tokens: dict[str, int] = {}
    latency: dict[str, float] = {}
    product_cards: list[ProductCard] = []

    # Offline / no-key path: heuristic extract + search + template pitch
    if not _has_openai_key():
        debug.turn_flow.append("llm_decided_search")
        t0 = time.perf_counter()
        req = _heuristic_search_request(body)
        _apply_negation_backstop(req, body, debug)
        req.semantic_query = clean_query_for_embedding(req.semantic_query, req.exclude_terms)
        latency["extract"] = (time.perf_counter() - t0) * 1000
        debug.turn_flow.append("filters_extracted")
        debug.previous_filters = _PREV_FILTERS.get(body.session_id)
        debug.extracted_filters = req.model_dump()
        _PREV_FILTERS[body.session_id] = req.model_dump()
        hits, qdrant_query, fallback, hit_debugs, q_ms = search_products(
            req, country=body.country, tenant_id=tenant_id
        )
        latency["qdrant"] = q_ms
        debug.qdrant_query = qdrant_query
        debug.hits = hit_debugs
        debug.fallback = fallback
        debug.turn_flow.append("qdrant_query")
        debug.turn_flow.append(f"fallback_{fallback.action}" if fallback.triggered else "fallback_none")
        product_cards = _cards_from_hits(hits, body.country)
        inject = _inject_block(hits, body.country) if hits else "PRODUCT CARDS: (none found)"
        debug.injected_prompt_block = inject
        debug.turn_flow.append(f"injected_{len(hits)}_cards")
        if not hits:
            reply = "I couldn't find a match with those constraints. Want to relax the budget or category?"
        else:
            lines = ["Based on what you shared, here are options:"]
            for c in product_cards[:3]:
                lines.append(f"- [{c.id}] {c.title}: {c.pitch} — {c.price_display}")
            if fallback.triggered:
                lines.append(f"(Note: relaxed search via {fallback.action})")
            reply = "\n".join(lines)
        debug.turn_flow.append("llm_pitched")
        debug.tokens = tokens
        debug.latency_ms = latency
        return ChatResponse(reply=reply, product_cards=product_cards[:3], debug=debug)

    client = get_openai()
    model = chat_model()
    tools = [build_search_products_tool()]
    instructions = _system_prompt(body, tenant_id)
    input_items = _conversation_input(body)
    rkw = responses_kwargs()

    t0 = time.perf_counter()
    first = client.responses.create(
        model=model,
        instructions=instructions,
        input=input_items,
        tools=tools,
        tool_choice="auto",
        **rkw,
    )
    latency["extract"] = (time.perf_counter() - t0) * 1000
    tokens["query_understanding"] = _usage_total(first)
    reasoning_understand = _reasoning_tokens(first)
    if reasoning_understand:
        tokens["reasoning_understand"] = reasoning_understand
    debug.reasoning_summary_understand = _reasoning_summary(first)

    tool_call = _first_function_call(first)
    if not tool_call:
        debug.turn_flow.append("llm_decided_no_search")
        reply = getattr(first, "output_text", None) or ""
        debug.tokens = tokens
        debug.latency_ms = latency
        return ChatResponse(reply=reply, product_cards=[], debug=debug)

    debug.turn_flow.append("llm_decided_search")
    try:
        args = json.loads(tool_call.arguments)
        req = parse_search_request(args)
    except Exception:
        debug.turn_flow.append("filter_parse_retry")
        retry = client.responses.create(
            model=model,
            previous_response_id=first.id,
            input=[
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps(
                        {"error": "invalid SearchRequest JSON, retry with valid fields"}
                    ),
                }
            ],
            tools=tools,
            tool_choice={"type": "function", "name": "search_products"},
            **rkw,
        )
        tokens["query_understanding"] = tokens.get("query_understanding", 0) + _usage_total(retry)
        retry_reasoning = _reasoning_tokens(retry)
        if retry_reasoning:
            tokens["reasoning_understand"] = tokens.get("reasoning_understand", 0) + retry_reasoning
        retry_summary = _reasoning_summary(retry)
        if retry_summary:
            debug.reasoning_summary_understand = (
                f"{debug.reasoning_summary_understand}\n\n{retry_summary}"
                if debug.reasoning_summary_understand
                else retry_summary
            )
        tool_call = _first_function_call(retry)
        if not tool_call:
            debug.tokens = tokens
            debug.latency_ms = latency
            return ChatResponse(
                reply=getattr(retry, "output_text", None)
                or "I had trouble understanding filters. Could you rephrase?",
                debug=debug,
            )
        first = retry  # continue tool round-trip from this response
        try:
            args = json.loads(tool_call.arguments)
            req = parse_search_request(args)
        except Exception:
            req = SearchRequest(
                semantic_query=body.messages[-1].content if body.messages else "products"
            )

    _apply_negation_backstop(req, body, debug)
    req.semantic_query = clean_query_for_embedding(req.semantic_query, req.exclude_terms)
    debug.turn_flow.append("filters_extracted")
    debug.previous_filters = _PREV_FILTERS.get(body.session_id)
    debug.extracted_filters = req.model_dump()
    _PREV_FILTERS[body.session_id] = req.model_dump()

    hits, qdrant_query, fallback, hit_debugs, q_ms = search_products(
        req, country=body.country, tenant_id=tenant_id
    )
    latency["qdrant"] = q_ms
    debug.qdrant_query = qdrant_query
    debug.hits = hit_debugs
    debug.fallback = fallback
    debug.turn_flow.append("qdrant_query")
    if fallback.triggered:
        debug.turn_flow.append(f"fallback_{fallback.action}")
    else:
        debug.turn_flow.append("fallback_none")

    product_cards = _cards_from_hits(hits, body.country)
    inject = _inject_block(hits, body.country) if hits else "PRODUCT CARDS: (none found)"
    debug.injected_prompt_block = inject
    debug.turn_flow.append(f"injected_{len(hits)}_cards")

    tool_payload = {
        "hit_count": len(hits),
        "fallback": fallback.model_dump(),
        "cards": inject,
        "guidance": (
            "Ask one narrowing question"
            if len(hits) > 12 or not hits
            else "Pitch up to 3 products with [ID] refs"
        ),
    }

    t1 = time.perf_counter()
    final = client.responses.create(
        model=model,
        previous_response_id=first.id,
        input=[
            {
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": json.dumps(tool_payload),
            }
        ],
        tools=tools,
        **rkw,
    )
    latency["final_llm"] = (time.perf_counter() - t1) * 1000
    tokens["final"] = _usage_total(final)
    reasoning_final = _reasoning_tokens(final)
    if reasoning_final:
        tokens["reasoning_final"] = reasoning_final
    debug.reasoning_summary_final = _reasoning_summary(final)

    reply = getattr(final, "output_text", None) or ""
    debug.turn_flow.append("llm_pitched")
    debug.tokens = tokens
    debug.latency_ms = latency
    return ChatResponse(reply=reply, product_cards=product_cards[:3], debug=debug)
