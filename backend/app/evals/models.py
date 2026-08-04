"""Pydantic models for eval scenarios, drafts, runs, and rubric scores."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SoftScenarioExpectations(BaseModel):
    must_use_search: bool = True
    expected_category_hints: list[str] = Field(default_factory=list)
    expected_facet_keys: list[str] = Field(default_factory=list)
    must_not_domains: list[str] = Field(default_factory=list)
    relevance_notes: str = ""


class ScenarioTestCase(BaseModel):
    id: str
    intent: str
    constraints: list[str] = Field(default_factory=list)


class EvalScenario(BaseModel):
    id: str
    source: Literal["auto", "user"] = "auto"
    title: str
    description: str
    soft_expectations: SoftScenarioExpectations = Field(default_factory=SoftScenarioExpectations)
    goal: str = ""
    max_turns: int = 6
    seed_opening: str | None = None
    test_cases: list[ScenarioTestCase] = Field(default_factory=list)


class ScenarioBankOut(BaseModel):
    scenarios: list[EvalScenario]


class ClarifyQuestion(BaseModel):
    id: str
    question: str


class DraftClarifyOut(BaseModel):
    questions: list[ClarifyQuestion]


class ConfirmScenarioOut(BaseModel):
    scenario: EvalScenario


class QueryAgentTurn(BaseModel):
    user_message: str
    goal_met: bool = False
    rationale: str = ""


class RubricDimensionScore(BaseModel):
    dimension: str
    pass_: bool = Field(alias="pass")
    reasoning: str = ""

    model_config = {"populate_by_name": True}


class TurnRubric(BaseModel):
    pass_: bool = Field(alias="pass", default=False)
    scores: list[RubricDimensionScore] = Field(default_factory=list)
    reasoning: str = ""
    judge_source: Literal["promptfoo", "openai_fallback", "stub"] = "stub"

    model_config = {"populate_by_name": True}


class RubricJudgeOut(BaseModel):
    """Forced-tool schema for OpenAI fallback judge."""

    tool_args_pass: bool
    tool_args_reasoning: str
    facets_filters_pass: bool
    facets_filters_reasoning: str
    empty_or_wrong_pass: bool
    empty_or_wrong_reasoning: str
    ranking_relevance_pass: bool
    ranking_relevance_reasoning: str
    product_ids_pass: bool
    product_ids_reasoning: str
    overall_pass: bool
    overall_reasoning: str


class StartEvalRunRequest(BaseModel):
    scenario_ids: list[str] | None = None
    country: str = "IN"
    max_turns: int | None = None


class ScenarioDraftRequest(BaseModel):
    description: str


class ScenarioConfirmRequest(BaseModel):
    draft_id: str
    answers: dict[str, str] = Field(default_factory=dict)


class GenerateScenariosRequest(BaseModel):
    count: int = 5
    replace: bool = False


class EvalRunProgress(BaseModel):
    run_id: str
    status: Literal["pending", "running", "done", "error"] = "pending"
    message: str = ""
    scenario_id: str | None = None
    turn: int | None = None
    detail: dict[str, Any] | None = None
