"""Aggregate run traces into conclusion.json / conclusion.md."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


PASS_THRESHOLD = 0.7


def summarize_promptfoo_results(raw: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Extract a small supplementary summary from promptfoo JSON output."""
    results = raw.get("results") if isinstance(raw, dict) else None
    if not isinstance(results, dict):
        results = raw if isinstance(raw, dict) else {}

    stats = results.get("stats") if isinstance(results, dict) else None
    if isinstance(stats, dict):
        successes = int(stats.get("successes") or stats.get("passes") or 0)
        failures = int(stats.get("failures") or stats.get("fails") or 0)
        total = successes + failures
        if total == 0:
            total = int(stats.get("tests") or 0) or successes
        return {
            "source": "promptfoo",
            "supplementary": True,
            "passes": successes,
            "fails": failures,
            "total": total or successes + failures,
            "pass_rate": round(successes / total, 3) if total else None,
        }

    # Fallback: count rows in results.table / results.results
    table = None
    if isinstance(results, dict):
        table = results.get("table") or results.get("results")
    if isinstance(table, list) and table:
        passes = 0
        fails = 0
        for row in table:
            if not isinstance(row, dict):
                continue
            success = row.get("success")
            if success is None:
                success = (row.get("score") or 0) >= 1
            if success:
                passes += 1
            else:
                fails += 1
        total = passes + fails
        return {
            "source": "promptfoo",
            "supplementary": True,
            "passes": passes,
            "fails": fails,
            "total": total,
            "pass_rate": round(passes / total, 3) if total else None,
        }

    return {
        "source": "promptfoo",
        "supplementary": True,
        "passes": None,
        "fails": None,
        "total": None,
        "pass_rate": None,
        "note": "promptfoo results present but stats could not be parsed",
    }


def build_conclusion(
    run_dir: Path,
    manifest: dict[str, Any],
    scenario_results: list[dict[str, Any]],
    *,
    promptfoo_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dim_pass: Counter[str] = Counter()
    dim_total: Counter[str] = Counter()
    themes: Counter[str] = Counter()
    judge_source_counts: Counter[str] = Counter()
    per_scenario: list[dict[str, Any]] = []

    for sr in scenario_results:
        turns = sr.get("turns") or []
        turn_pass = 0
        searched = False
        for t in turns:
            if t.get("extracted_filters"):
                searched = True
            rubric = t.get("rubric") or {}
            src = rubric.get("judge_source") or "stub"
            judge_source_counts[src] += 1
            if rubric.get("pass"):
                turn_pass += 1
            for s in rubric.get("scores") or []:
                dim = s.get("dimension") or "unknown"
                dim_total[dim] += 1
                if s.get("pass"):
                    dim_pass[dim] += 1
                elif s.get("reasoning"):
                    themes[f"{dim}: {s['reasoning'][:120]}"] += 1
            if rubric.get("reasoning") and not rubric.get("pass"):
                themes[rubric["reasoning"][:160]] += 1

        must_search = ((sr.get("soft_expectations") or {}).get("must_use_search", True))
        if not turns:
            per_scenario.append(
                {
                    "scenario_id": sr.get("scenario_id"),
                    "title": sr.get("title"),
                    "verdict": "skipped",
                    "turn_pass_rate": None,
                    "turns": 0,
                    "searched": False,
                    "must_use_search": must_search,
                }
            )
            continue

        n = len(turns)
        rate = turn_pass / n
        ok = rate >= PASS_THRESHOLD and (searched or not must_search)
        per_scenario.append(
            {
                "scenario_id": sr.get("scenario_id"),
                "title": sr.get("title"),
                "verdict": "pass" if ok else "fail",
                "turn_pass_rate": round(rate, 3),
                "turns": len(turns),
                "searched": searched,
                "must_use_search": must_search,
            }
        )

    scored = [p for p in per_scenario if p["verdict"] != "skipped"]
    scenario_pass = sum(1 for p in scored if p["verdict"] == "pass")
    total = len(scored) or 1
    overall_rate = scenario_pass / total if scored else 0.0
    if not scored:
        overall = "fail"
    elif overall_rate >= 0.85:
        overall = "pass"
    elif overall_rate >= 0.5:
        overall = "flaky"
    else:
        overall = "fail"

    dim_rates = {
        d: round(dim_pass[d] / dim_total[d], 3) if dim_total[d] else None for d in sorted(dim_total)
    }

    conclusion: dict[str, Any] = {
        "overall": overall,
        "scenario_pass_rate": round(overall_rate, 3),
        "scenarios_passed": scenario_pass,
        "scenarios_total": len(scored),
        "scenarios_skipped": sum(1 for p in per_scenario if p["verdict"] == "skipped"),
        "dimension_pass_rates": dim_rates,
        "per_scenario": per_scenario,
        "failure_themes": [{"theme": t, "count": c} for t, c in themes.most_common(12)],
        "judge_source_counts": dict(judge_source_counts),
        "manifest": {
            "run_id": manifest.get("run_id"),
            "tenant_id": manifest.get("tenant_id"),
            "country": manifest.get("country"),
            "missing_scenario_ids": manifest.get("missing_scenario_ids") or [],
        },
    }
    if promptfoo_summary is not None:
        conclusion["promptfoo_summary"] = promptfoo_summary

    (run_dir / "conclusion.json").write_text(
        json.dumps(conclusion, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "conclusion.md").write_text(_to_markdown(conclusion), encoding="utf-8")
    return conclusion


def _to_markdown(c: dict[str, Any]) -> str:
    lines = [
        f"# Eval conclusion: **{c['overall']}**",
        "",
        f"- Scenarios passed: {c['scenarios_passed']}/{c['scenarios_total']} "
        f"(rate {c['scenario_pass_rate']})",
    ]
    skipped = c.get("scenarios_skipped") or 0
    if skipped:
        lines.append(f"- Scenarios skipped (0 turns): {skipped}")
    lines.append(
        f"- Tenant: `{c.get('manifest', {}).get('tenant_id')}` · "
        f"Run: `{c.get('manifest', {}).get('run_id')}`"
    )
    jsc = c.get("judge_source_counts") or {}
    if jsc:
        lines.append(
            "- Judge sources: "
            + ", ".join(f"{k}={v}" for k, v in sorted(jsc.items()))
        )
        stub_n = int(jsc.get("stub") or 0)
        total_judged = sum(int(v) for v in jsc.values()) or 0
        if stub_n > 0:
            lines.append(
                f"- **Warning:** {stub_n} of {total_judged} turns judged by fallback "
                f"heuristic (stub), not the LLM judge."
            )
    pf = c.get("promptfoo_summary")
    if isinstance(pf, dict):
        lines += [
            "",
            "## Promptfoo (supplementary)",
            "",
            f"- Passes: {pf.get('passes')}/{pf.get('total')} "
            f"(rate {pf.get('pass_rate')}) — not blended into overall verdict",
        ]
        if pf.get("note"):
            lines.append(f"- Note: {pf['note']}")
    missing = (c.get("manifest") or {}).get("missing_scenario_ids") or []
    if missing:
        lines += ["", f"- Missing requested scenario ids: {', '.join(missing)}"]
    lines += ["", "## Dimension pass rates", ""]
    for dim, rate in (c.get("dimension_pass_rates") or {}).items():
        lines.append(f"- `{dim}`: {rate}")
    lines += ["", "## Per scenario", ""]
    for p in c.get("per_scenario") or []:
        rate = p.get("turn_pass_rate")
        rate_s = "n/a" if rate is None else str(rate)
        lines.append(
            f"- **{p['verdict']}** `{p['scenario_id']}` — turn pass rate {rate_s} "
            f"({p['turns']} turns, searched={p['searched']})"
        )
    lines += ["", "## Failure themes", ""]
    themes = c.get("failure_themes") or []
    if not themes:
        lines.append("- (none)")
    else:
        for t in themes:
            lines.append(f"- ({t['count']}) {t['theme']}")
    lines.append("")
    return "\n".join(lines)
