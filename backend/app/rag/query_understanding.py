"""Query understanding — SearchRequest tool schema helpers."""

from __future__ import annotations

from app.pipeline.s2_normalize import load_vocab
from app.schemas import SearchRequest


def _category_path_description() -> str:
    paths = load_vocab().get("category_paths") or []
    if not paths:
        return "Category path from vocabulary, or null"
    return "One of: " + ", ".join(paths)


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
                "billing_period": {
                    "type": ["string", "null"],
                    "description": "one_time | monthly | annual",
                },
                "top_k": {"type": "integer", "default": 8},
            },
            "required": ["semantic_query"],
            "additionalProperties": False,
        },
    }


# Built at import for callers that expect a module-level constant; rebuild if vocab changes at runtime.
SEARCH_PRODUCTS_TOOL = build_search_products_tool()


def parse_search_request(args: dict) -> SearchRequest:
    return SearchRequest.model_validate(args)
