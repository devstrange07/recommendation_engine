"""Judge search_products retrieval via promptfoo or OpenAI fallback."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from app.evals.models import (
    RankingOrderExpectation,
    RubricDimensionScore,
    RubricJudgeOut,
    TurnRubric,
)
from app.openai_client import call_with_forced_tool, chat_key_present, chat_model

REPO_ROOT = Path(__file__).resolve().parents[3]
EVALS_DIR = REPO_ROOT / "evals"
PROMPTFOO_CONFIG = EVALS_DIR / "promptfooconfig.yaml"
JUDGE_PROMPT = EVALS_DIR / "prompts" / "retrieval_judge.txt"

DIMENSIONS = (
    "tool_args",
    "facets_filters",
    "empty_or_wrong",
    "ranking_relevance",
    "product_ids",
)

_TITLE_KWH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*kWh", re.IGNORECASE)


def build_retrieval_blob(
    *,
    scenario: dict[str, Any],
    soft_expectations: dict[str, Any],
    user_message: str,
    extracted_filters: dict[str, Any] | None,
    hits: list[dict[str, Any]],
    fallback: dict[str, Any] | None,
) -> dict[str, Any]:
    hit_summaries = []
    for h in hits[:8]:
        excerpt = h.get("payload_excerpt") or {}
        title = excerpt.get("title") or excerpt.get("name") or h.get("title")
        price_min = excerpt.get("price_min") if excerpt else None
        if price_min is None:
            price_min = h.get("price_min")
        hit_summaries.append(
            {
                "id": h.get("id"),
                "rrf_rank": h.get("rrf_rank"),
                "title": title,
                "category_path": excerpt.get("category_path") or h.get("category_path"),
                "price_min": price_min,
            }
        )
    return {
        "scenario": {
            "id": scenario.get("id"),
            "title": scenario.get("title"),
            "description": scenario.get("description"),
            "goal": scenario.get("goal"),
            "soft_expectations": soft_expectations,
        },
        "user_message": user_message,
        "search_products_args": extracted_filters,
        "hits": hit_summaries,
        "fallback": fallback,
        "searched": extracted_filters is not None,
    }


def _hit_title(hit: dict[str, Any]) -> str:
    excerpt = hit.get("payload_excerpt") or {}
    return str(excerpt.get("title") or excerpt.get("name") or hit.get("title") or "")


def _hit_price_min(hit: dict[str, Any], currency: str) -> float | None:
    excerpt = hit.get("payload_excerpt") or {}
    price_min = excerpt.get("price_min") if excerpt else None
    if price_min is None:
        price_min = hit.get("price_min")
    if isinstance(price_min, dict):
        raw = price_min.get(currency)
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    if isinstance(price_min, (int, float)):
        return float(price_min)
    return None


def _hit_title_kwh(hit: dict[str, Any]) -> float | None:
    m = _TITLE_KWH_RE.search(_hit_title(hit))
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def _extract_order_value(
    hit: dict[str, Any],
    spec: RankingOrderExpectation,
) -> float | None:
    if spec.field == "price_min":
        return _hit_price_min(hit, spec.currency)
    if spec.field == "title_kwh":
        return _hit_title_kwh(hit)
    return None


def ranking_order_check(
    hits: list[dict[str, Any]],
    spec: RankingOrderExpectation | dict[str, Any] | None,
    user_message: str,
) -> tuple[bool, bool, str]:
    """Return (applies, ok, reason).

    If the assert does not apply, ok is True and reason explains why.
    """
    if spec is None:
        return False, True, "no ranking_order expectation"
    if isinstance(spec, dict):
        try:
            spec = RankingOrderExpectation.model_validate(spec)
        except Exception as e:
            return False, True, f"invalid ranking_order: {e}"

    msg = user_message or ""
    if spec.apply_if:
        msg_cf = msg.casefold()
        if not any(token.casefold() in msg_cf for token in spec.apply_if if token):
            return False, True, "ranking_order apply_if did not match user_message"

    ranked = sorted(
        hits,
        key=lambda h: (h.get("rrf_rank") is None, h.get("rrf_rank") if h.get("rrf_rank") is not None else 0),
    )
    values: list[tuple[Any, float]] = []
    for h in ranked:
        val = _extract_order_value(h, spec)
        if val is None:
            continue
        values.append((h.get("id"), val))

    if len(values) < 2:
        return True, True, f"ranking_order skipped: fewer than 2 extractable {spec.field} values"

    for i in range(1, len(values)):
        prev_id, prev_v = values[i - 1]
        cur_id, cur_v = values[i]
        if spec.direction == "asc" and cur_v < prev_v:
            return (
                True,
                False,
                f"ranking_order {spec.field} asc violated: {prev_id}={prev_v} before {cur_id}={cur_v}",
            )
        if spec.direction == "desc" and cur_v > prev_v:
            return (
                True,
                False,
                f"ranking_order {spec.field} desc violated: {prev_id}={prev_v} before {cur_id}={cur_v}",
            )
    return True, True, f"ranking_order {spec.field} {spec.direction} ok ({len(values)} values)"


def apply_ranking_order_hard_fail(
    rubric: TurnRubric,
    *,
    hits: list[dict[str, Any]],
    soft_expectations: dict[str, Any] | None,
    user_message: str,
) -> TurnRubric:
    """Force ranking_relevance + overall fail when numeric order is violated."""
    spec = (soft_expectations or {}).get("ranking_order")
    applies, ok, reason = ranking_order_check(hits, spec, user_message)
    if not applies or ok:
        return rubric

    scores: list[RubricDimensionScore] = []
    for s in rubric.scores:
        if s.dimension == "ranking_relevance":
            scores.append(
                RubricDimensionScore(
                    dimension="ranking_relevance",
                    **{"pass": False},
                    reasoning=(s.reasoning + " | " if s.reasoning else "") + reason,
                )
            )
        else:
            scores.append(s)
    if not any(s.dimension == "ranking_relevance" for s in scores):
        scores.append(
            RubricDimensionScore(
                dimension="ranking_relevance",
                **{"pass": False},
                reasoning=reason,
            )
        )

    overall_reason = (rubric.reasoning or "").strip()
    if reason not in overall_reason:
        overall_reason = (overall_reason + " | " if overall_reason else "") + reason

    return TurnRubric(
        **{"pass": False},
        scores=scores,
        reasoning=overall_reason,
        judge_source=rubric.judge_source,
    )


def _stub_rubric(blob: dict[str, Any]) -> TurnRubric:
    searched = bool(blob.get("searched"))
    hits = blob.get("hits") or []
    must = (blob.get("scenario") or {}).get("soft_expectations") or {}
    must_search = must.get("must_use_search", True)
    scores = []
    for dim in DIMENSIONS:
        if dim == "tool_args":
            ok = searched or not must_search
            reason = "search called" if searched else "no search_products call"
        elif dim == "empty_or_wrong":
            ok = (not must_search) or (searched and len(hits) > 0)
            reason = f"hits={len(hits)}"
        elif dim == "product_ids":
            ok = all(h.get("id") for h in hits) if hits else (not must_search or not searched)
            reason = "ids present" if ok else "missing hit ids"
        else:
            ok = searched
            reason = "stub heuristic"
        scores.append(RubricDimensionScore(dimension=dim, **{"pass": ok}, reasoning=reason))
    overall = all(s.pass_ for s in scores) if scores else False
    return TurnRubric(
        **{"pass": overall},
        scores=scores,
        reasoning="stub judge (no LLM/promptfoo)",
        judge_source="stub",
    )


def _openai_rubric(blob: dict[str, Any]) -> TurnRubric:
    prompt = ""
    if JUDGE_PROMPT.exists():
        prompt = JUDGE_PROMPT.read_text(encoding="utf-8")
    out = call_with_forced_tool(
        messages=[
            {
                "role": "system",
                "content": prompt
                or (
                    "Judge product retrieval quality for search_products. "
                    "Score each rubric dimension true/false with short reasoning."
                ),
            },
            {"role": "user", "content": json.dumps(blob, ensure_ascii=False)},
        ],
        tool_name="submit_retrieval_rubric",
        tool_description="Submit retrieval rubric scores",
        parameters_model=RubricJudgeOut,
        validate=RubricJudgeOut.model_validate,
    )
    scores = [
        RubricDimensionScore(
            dimension="tool_args",
            **{"pass": out.tool_args_pass},
            reasoning=out.tool_args_reasoning,
        ),
        RubricDimensionScore(
            dimension="facets_filters",
            **{"pass": out.facets_filters_pass},
            reasoning=out.facets_filters_reasoning,
        ),
        RubricDimensionScore(
            dimension="empty_or_wrong",
            **{"pass": out.empty_or_wrong_pass},
            reasoning=out.empty_or_wrong_reasoning,
        ),
        RubricDimensionScore(
            dimension="ranking_relevance",
            **{"pass": out.ranking_relevance_pass},
            reasoning=out.ranking_relevance_reasoning,
        ),
        RubricDimensionScore(
            dimension="product_ids",
            **{"pass": out.product_ids_pass},
            reasoning=out.product_ids_reasoning,
        ),
    ]
    return TurnRubric(
        **{"pass": out.overall_pass},
        scores=scores,
        reasoning=out.overall_reasoning,
        judge_source="openai_fallback",
    )


def _promptfoo_available() -> bool:
    if not PROMPTFOO_CONFIG.exists():
        return False
    return shutil.which("npx") is not None or shutil.which("npx.cmd") is not None


def _run_promptfoo(cases: list[dict[str, Any]], run_dir: Path) -> dict[str, Any] | None:
    tests_path = run_dir / "pf-tests.yaml"
    tests_path.write_text(yaml.safe_dump(cases, sort_keys=False, allow_unicode=True), encoding="utf-8")
    out_path = run_dir / "promptfoo-results.json"
    npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    cmd = [
        npx,
        "--yes",
        "promptfoo",
        "eval",
        "-c",
        str(PROMPTFOO_CONFIG),
        "--tests",
        str(tests_path),
        "-o",
        str(out_path),
    ]
    env = os.environ.copy()
    try:
        subprocess.run(
            cmd,
            cwd=str(EVALS_DIR),
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
            shell=False,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        print(f"WARN: promptfoo eval failed: {e}")
        return None
    if not out_path.exists():
        return None
    try:
        return json.loads(out_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def judge_turn(
    blob: dict[str, Any],
    *,
    prefer_promptfoo: bool = True,
) -> TurnRubric:
    """Judge a single turn. Promptfoo is used in batch by the runner; per-turn uses OpenAI/stub."""
    if chat_key_present():
        try:
            rubric = _openai_rubric(blob)
        except Exception as e:
            print(f"WARN: openai rubric failed: {e}")
            rubric = _stub_rubric(blob)
    else:
        rubric = _stub_rubric(blob)

    soft = ((blob.get("scenario") or {}).get("soft_expectations") or {})
    return apply_ranking_order_hard_fail(
        rubric,
        hits=list(blob.get("hits") or []),
        soft_expectations=soft,
        user_message=str(blob.get("user_message") or ""),
    )


def write_promptfoo_cases(
    run_dir: Path,
    cases: list[dict[str, Any]],
    *,
    prefer_promptfoo: bool = True,
) -> Path:
    """Write promptfoo test cases for optional batch re-eval / HTML report."""
    tests_path = run_dir / "pf-tests.yaml"
    # promptfoo test list format
    docs = []
    for c in cases:
        docs.append(
            {
                "vars": {
                    "retrieval_blob": json.dumps(c["blob"], ensure_ascii=False),
                    "scenario_id": c.get("scenario_id", ""),
                    "turn": c.get("turn", 0),
                },
                "assert": [
                    {
                        "type": "llm-rubric",
                        "value": (
                            "Pass only if search_products tool args and retrieved hits are "
                            "reasonable vs the scenario soft_expectations in the retrieval JSON. "
                            "Fail if product-seeking with must_use_search but no search, "
                            "wrong-domain flooding, or empty hits when intent is clear."
                        ),
                    }
                ],
            }
        )
    tests_path.write_text(yaml.safe_dump(docs, sort_keys=False, allow_unicode=True), encoding="utf-8")
    if prefer_promptfoo and _promptfoo_available():
        _run_promptfoo(docs, run_dir)
    return tests_path


def default_judge_model() -> str:
    return chat_model()
