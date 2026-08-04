"""Query understanding — SearchRequest tool schema helpers."""

from __future__ import annotations

from app.pipeline.s2_normalize import load_vocab
from app.schemas import SearchRequest


def _category_path_description() -> str:
    paths = load_vocab().get("category_paths") or []
    if not paths:
        return "Category path from vocabulary, or null"
    return "One of: " + ", ".join(paths)


def _facet_filter_description() -> str:
    vocab = load_vocab()
    facet_schemas = vocab.get("facet_schemas") or {}
    if not facet_schemas:
        return "Structured attribute filters (key/value pairs from facet vocabulary)"
    lines = [
        "Structured filters on product attributes. Available keys by domain:",
    ]
    for domain, facets in facet_schemas.items():
        filterable = [f for f in (facets or []) if f.get("filterable")]
        if not filterable:
            continue
        keys = [f"{f['key']} ({f.get('type', 'string')})" for f in filterable]
        lines.append(f"  {domain}: {', '.join(keys)}")
    lines.append("Use op='eq' for exact match, 'lte'/'gte' for numeric ranges, 'contains' for text.")
    return "\n".join(lines)


def build_search_products_tool() -> dict:
    """Responses API flat function-tool schema."""
    return {
        "type": "function",
        "name": "search_products",
        "description": (
            "Extract the user's cumulative product requirements from the full conversation "
            "as of the latest message. Rewrite, don't append. Extract bare numbers for price_max; "
            "the server binds currency from the session country.\n\n"
            "CRITICAL negation handling: whenever the user excludes something with language like "
            "'not X', 'no X', 'except X', 'without X', 'excluding X', 'other than X', or 'besides X', "
            "you MUST do BOTH every time.\n"
            "1) Put X (short and specific: brand, ingredient, material, feature, etc.) into exclude_terms.\n"
            "2) Remove X and the full negation phrase from semantic_query. semantic_query must never "
            "contain the excluded term or negation phrasing that references it.\n\n"
            "Example: 'show me phones other than Samsung' -> semantic_query='phones', "
            "exclude_terms=['Samsung']. WRONG: semantic_query='phones other than Samsung'.\n"
            "Example: 'almond chocolates, but not from Lindt' -> semantic_query='almond chocolates', "
            "exclude_terms=['Lindt'].\n\n"
            "When the user mentions specific product attributes (e.g. '22K gold', 'petrol car', "
            "'5mg tablet', 'under 6 grams'), extract them as attribute_filters with matching facet "
            "keys from the vocabulary.\n"
            "Example: '22K gold necklaces under 6 grams' -> attribute_filters=["
            "{key:'purity', op:'eq', value:'22K'}, {key:'weight_g', op:'lte', value:6}].\n\n"
            "Call this before recommending products."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "semantic_query": {
                    "type": "string",
                    "description": "Rewritten cumulative intent for semantic search",
                },
                "category_path": {
                    "type": ["string", "null"],
                    "description": _category_path_description(),
                },
                "use_case_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "target_audience": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "exclude_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Anything the user explicitly wants excluded (brand, ingredient, material, "
                        "feature, color, or other noun phrase) from negation language such as "
                        "'not X', 'no X', 'except X', 'without X', 'excluding X', 'other than X'. "
                        "Keep X short and specific, and never leave it in semantic_query."
                    ),
                },
                "price_max": {
                    "type": ["number", "null"],
                    "description": "Max price as a bare number in the user's currency",
                },
                "pricing_type": {
                    "type": ["string", "null"],
                    "description": "one_time | recurring | usage | quote",
                },
                "kind": {
                    "type": ["string", "null"],
                    "description": (
                        "One of: physical_good, digital_good, service, subscription, "
                        "bundle, experience, venue_offering, financial_product"
                    ),
                },
                "brand": {
                    "type": ["string", "null"],
                    "description": "Brand or manufacturer name to filter by",
                },
                "attribute_filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "op": {
                                "type": "string",
                                "enum": ["eq", "lte", "gte", "contains"],
                            },
                            "value": {},
                        },
                        "required": ["key", "value"],
                        "additionalProperties": False,
                    },
                    "description": _facet_filter_description(),
                },
                "top_k": {"type": "integer", "default": 8},
            },
            "required": ["semantic_query"],
            "additionalProperties": False,
        },
    }


def build_search_products_tool_completions() -> dict:
    """Chat Completions nested function-tool schema (DeepSeek / OpenAI completions)."""
    flat = build_search_products_tool()
    return {
        "type": "function",
        "function": {
            "name": flat["name"],
            "description": flat["description"],
            "parameters": flat["parameters"],
        },
    }


# Built at import for callers that expect a module-level constant; rebuild if vocab changes at runtime.
SEARCH_PRODUCTS_TOOL = build_search_products_tool()


def parse_search_request(args: dict) -> SearchRequest:
    return SearchRequest.model_validate(args)
