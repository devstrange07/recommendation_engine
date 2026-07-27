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
    return {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Extract the user's cumulative product requirements from the full conversation "
                "as of the latest message. Rewrite, don't append. Extract bare numbers for price_max; "
                "the server binds currency from the session country. Call this before recommending products."
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
        },
    }


# Built at import for callers that expect a module-level constant; rebuild if vocab changes at runtime.
SEARCH_PRODUCTS_TOOL = build_search_products_tool()


def parse_search_request(args: dict) -> SearchRequest:
    return SearchRequest.model_validate(args)
