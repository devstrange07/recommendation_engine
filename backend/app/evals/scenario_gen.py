"""LLM auto-generation of eval scenarios from catalog_profile."""

from __future__ import annotations

import json

from app.evals.models import EvalScenario, ScenarioBankOut, SoftScenarioExpectations, ScenarioTestCase
from app.evals.profile import load_catalog_profile, generate_catalog_profile
from app.evals.scenario_store import list_scenarios, save_scenario
from app.openai_client import call_with_forced_tool, chat_key_present


def _heuristic_scenarios(profile: dict, count: int) -> list[EvalScenario]:
    domains = profile.get("domains") or []
    soft = profile.get("soft_expectations") or {}
    out: list[EvalScenario] = []
    for i, d in enumerate(domains[:count]):
        cat = d.get("category_path") or f"domain_{i}"
        sid = f"auto_{cat.lower().replace('/', '_')}"[:64]
        facets = d.get("facet_keys") or []
        title_sample = (d.get("sample_titles") or ["products"])[0]
        out.append(
            EvalScenario(
                id=sid,
                source="auto",
                title=f"Browse {cat}",
                description=f"Shopper exploring {cat}, similar to {title_sample}.",
                soft_expectations=SoftScenarioExpectations(
                    must_use_search=True,
                    expected_category_hints=[cat],
                    expected_facet_keys=facets[:4],
                    must_not_domains=list(soft.get("out_of_scope_domains") or [])[:5],
                    relevance_notes=f"Hits should be in {cat}",
                ),
                goal=f"User narrowed intent within {cat} and search returned in-domain hits.",
                max_turns=6,
                test_cases=[
                    ScenarioTestCase(
                        id="tc1",
                        intent=f"Looking for {cat}",
                        constraints=list(soft.get("typical_constraints") or [])[:3],
                    )
                ],
            )
        )
    if not out:
        out.append(
            EvalScenario(
                id="auto_generic_browse",
                source="auto",
                title="Generic product browse",
                description="User looks for something in the catalog.",
                soft_expectations=SoftScenarioExpectations(
                    must_use_search=True,
                    expected_category_hints=list(soft.get("in_scope_domains") or [])[:3],
                    relevance_notes="Hits should match catalog domains",
                ),
                goal="Search ran and returned in-catalog products.",
                test_cases=[ScenarioTestCase(id="tc1", intent="Show me products", constraints=[])],
            )
        )
    return out[:count]


def generate_scenarios(
    tenant_id: str,
    *,
    count: int = 5,
    replace: bool = False,
) -> list[EvalScenario]:
    profile = load_catalog_profile(tenant_id)
    if profile is None:
        profile = generate_catalog_profile(tenant_id)

    existing = list_scenarios(tenant_id)
    if existing and not replace:
        return existing

    if replace:
        from app.evals.scenario_store import delete_scenario

        for sc in existing:
            if sc.source == "auto":
                delete_scenario(tenant_id, sc.id)

    if chat_key_present():
        try:
            compact = {
                "overview": profile.get("overview"),
                "soft_expectations": profile.get("soft_expectations"),
                "domains": [
                    {
                        "category_path": d.get("category_path"),
                        "count": d.get("count"),
                        "facet_keys": (d.get("facet_keys") or [])[:8],
                        "sample_titles": (d.get("sample_titles") or [])[:3],
                    }
                    for d in (profile.get("domains") or [])[:15]
                ],
                "count": count,
            }
            bank = call_with_forced_tool(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Create retrieval eval scenarios for a product catalog chatbot. "
                            f"Return exactly {count} scenarios (or fewer if catalog is tiny). "
                            "Each scenario needs id, title, description, soft_expectations, goal, "
                            "max_turns=6, test_cases with intents/constraints. "
                            "source must be 'auto'. No gold product IDs. "
                            "Focus on search_products filter/retrieval quality."
                        ),
                    },
                    {"role": "user", "content": json.dumps(compact, ensure_ascii=False)},
                ],
                tool_name="submit_scenarios",
                tool_description="Submit generated eval scenarios",
                parameters_model=ScenarioBankOut,
                validate=ScenarioBankOut.model_validate,
            )
            scenarios = bank.scenarios
            for sc in scenarios:
                sc.source = "auto"
        except Exception as e:
            print(f"WARN: scenario LLM generate failed: {e}")
            scenarios = _heuristic_scenarios(profile, count)
    else:
        scenarios = _heuristic_scenarios(profile, count)

    saved: list[EvalScenario] = []
    for sc in scenarios[:count]:
        save_scenario(tenant_id, sc)
        saved.append(sc)
    return saved
