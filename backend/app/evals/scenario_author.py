"""UI two-phase user scenario authoring: draft clarifications → confirm → save."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.evals.models import (
    ClarifyQuestion,
    DraftClarifyOut,
    EvalScenario,
    SoftScenarioExpectations,
    ScenarioTestCase,
)
from app.evals.profile import load_catalog_profile, generate_catalog_profile
from app.evals.scenario_store import save_scenario
from app.openai_client import call_with_forced_tool, chat_key_present
from app.pipeline.paths import ensure_tenant_dirs


def _draft_path(tenant_id: str, draft_id: str) -> Path:
    paths = ensure_tenant_dirs(tenant_id)
    return paths.evals_drafts / f"{draft_id}.yaml"


def create_draft(tenant_id: str, description: str) -> dict:
    profile = load_catalog_profile(tenant_id)
    if profile is None:
        profile = generate_catalog_profile(tenant_id)

    description = (description or "").strip()
    if not description:
        raise ValueError("description is required")

    if chat_key_present():
        try:
            out = call_with_forced_tool(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "A user wants an eval scenario for product retrieval testing. "
                            "Ask 2–5 short clarifying questions so you can write precise soft "
                            "expectations and test cases. Do not ask for product IDs."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "description": description,
                                "catalog_overview": profile.get("overview"),
                                "in_scope_domains": (profile.get("soft_expectations") or {}).get(
                                    "in_scope_domains"
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                tool_name="submit_questions",
                tool_description="Submit clarifying questions",
                parameters_model=DraftClarifyOut,
                validate=DraftClarifyOut.model_validate,
            )
            questions = out.questions
        except Exception as e:
            print(f"WARN: draft clarify LLM failed: {e}")
            questions = _default_questions()
    else:
        questions = _default_questions()

    draft_id = uuid.uuid4().hex[:12]
    doc = {
        "draft_id": draft_id,
        "description": description,
        "questions": [q.model_dump() for q in questions],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _draft_path(tenant_id, draft_id)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {"draft_id": draft_id, "questions": [q.model_dump() for q in questions]}


def _default_questions() -> list[ClarifyQuestion]:
    return [
        ClarifyQuestion(id="q1", question="Which category or product type should retrieval target?"),
        ClarifyQuestion(id="q2", question="Any budget, brand, or attribute constraints?"),
        ClarifyQuestion(id="q3", question="What would count as a wrong-domain result for this scenario?"),
    ]


def confirm_draft(tenant_id: str, draft_id: str, answers: dict[str, str]) -> EvalScenario:
    path = _draft_path(tenant_id, draft_id)
    if not path.exists():
        raise FileNotFoundError(f"draft {draft_id} not found")
    draft = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    description = draft.get("description") or ""
    profile = load_catalog_profile(tenant_id) or {}

    if chat_key_present():
        try:
            out = call_with_forced_tool(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Build one user-sourced retrieval eval scenario as the submit_scenario tool. "
                            "source must be 'user'. Include soft_expectations, goal, max_turns=6, "
                            "and test_cases. No gold product IDs."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "description": description,
                                "answers": answers,
                                "catalog_overview": profile.get("overview"),
                                "soft_expectations": profile.get("soft_expectations"),
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                tool_name="submit_scenario",
                tool_description="Submit the finalized eval scenario",
                parameters_model=EvalScenario,
                validate=EvalScenario.model_validate,
            )
            scenario = out
            scenario.source = "user"
        except Exception as e:
            print(f"WARN: confirm scenario LLM failed: {e}")
            scenario = _heuristic_from_draft(description, answers, profile)
    else:
        scenario = _heuristic_from_draft(description, answers, profile)

    save_scenario(tenant_id, scenario)
    try:
        path.unlink()
    except OSError:
        pass
    return scenario


def _heuristic_from_draft(
    description: str, answers: dict[str, str], profile: dict
) -> EvalScenario:
    soft = profile.get("soft_expectations") or {}
    cats = list(soft.get("in_scope_domains") or [])[:2]
    sid = "user_" + (description.lower().replace(" ", "_")[:40] or "scenario")
    constraints = [v for v in answers.values() if v]
    return EvalScenario(
        id=sid,
        source="user",
        title=description[:80] or "User scenario",
        description=description,
        soft_expectations=SoftScenarioExpectations(
            must_use_search=True,
            expected_category_hints=cats,
            must_not_domains=list(soft.get("out_of_scope_domains") or [])[:5],
            relevance_notes="; ".join(constraints)[:500],
        ),
        goal="User intent satisfied with in-domain search hits.",
        max_turns=6,
        test_cases=[
            ScenarioTestCase(id="tc1", intent=description, constraints=constraints[:5]),
        ],
    )
