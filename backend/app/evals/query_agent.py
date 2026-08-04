"""LLM decides the next user message for an eval scenario."""

from __future__ import annotations

import json
from typing import Any

from app.evals.models import EvalScenario, QueryAgentTurn
from app.openai_client import call_with_forced_tool, chat_key_present


def next_user_turn(
    *,
    scenario: EvalScenario,
    profile: dict[str, Any] | None,
    messages: list[dict[str, str]],
    last_retrieval: dict[str, Any] | None,
    turn_index: int,
) -> QueryAgentTurn:
    """Return next user message and whether the scenario goal is already met."""
    if turn_index == 1 and scenario.seed_opening:
        return QueryAgentTurn(
            user_message=scenario.seed_opening,
            goal_met=False,
            rationale="seed_opening",
        )

    if not messages and scenario.test_cases:
        tc = scenario.test_cases[0]
        parts = [tc.intent] + list(tc.constraints or [])
        return QueryAgentTurn(
            user_message=". ".join(p for p in parts if p),
            goal_met=False,
            rationale="seed from first test_case",
        )

    if chat_key_present():
        try:
            return call_with_forced_tool(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You play a shopper testing a product catalog chatbot. "
                            "Given the scenario, test cases, conversation, and last search_products "
                            "retrieval summary, write the NEXT user message. "
                            "Cover remaining test-case intents/constraints naturally across turns. "
                            "Set goal_met=true only when: soft constraints are present in the "
                            "conversation AND a product-seeking search has already run with "
                            "plausible in-domain hits (or you intentionally finished after search). "
                            "Do not mark goal_met on turn 1 unless seed already includes everything "
                            "and search already happened (it has not yet)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "scenario": scenario.model_dump(mode="json"),
                                "catalog_soft_expectations": (profile or {}).get("soft_expectations"),
                                "conversation": messages,
                                "last_retrieval": last_retrieval,
                                "turn_index": turn_index,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                tool_name="submit_next_turn",
                tool_description="Submit next shopper message and goal_met flag",
                parameters_model=QueryAgentTurn,
                validate=QueryAgentTurn.model_validate,
            )
        except Exception as e:
            print(f"WARN: query_agent LLM failed: {e}")

    return _heuristic_next(scenario, messages, turn_index)


def _heuristic_next(
    scenario: EvalScenario, messages: list[dict[str, str]], turn_index: int
) -> QueryAgentTurn:
    tcs = scenario.test_cases or []
    idx = min(turn_index - 1, max(len(tcs) - 1, 0))
    if tcs:
        tc = tcs[idx]
        msg = tc.intent
        if tc.constraints:
            msg = f"{msg}. " + ". ".join(tc.constraints)
    else:
        msg = scenario.description or "Show me relevant products"
    goal_met = turn_index >= min(scenario.max_turns, max(len(tcs), 2))
    # heuristic: only signal done after at least one assistant reply and we covered cases
    if len(messages) < 2:
        goal_met = False
    return QueryAgentTurn(user_message=msg, goal_met=goal_met, rationale="heuristic fallback")
