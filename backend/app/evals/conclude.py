"""Aggregate run traces into conclusion.json / conclusion.md."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PASS_THRESHOLD = 0.7


def build_conclusion(run_dir: Path, manifest: dict[str, Any], scenario_results: list[dict[str, Any]]) -> dict[str, Any]:
    dim_pass: Counter[str] = Counter()
    dim_total: Counter[str] = Counter()
    themes: Counter[str] = Counter()
    per_scenario: list[dict[str, Any]] = []

    for sr in scenario_results:
        turns = sr.get("turns") or []
        turn_pass = 0
        searched = False
        for t in turns:
            if t.get("extracted_filters"):
                searched = True
            rubric = t.get("rubric") or {}
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

        n = len(turns) or 1
        rate = turn_pass / n
        must_search = ((sr.get("soft_expectations") or {}).get("must_use_search", True))
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

    scenario_pass = sum(1 for p in per_scenario if p["verdict"] == "pass")
    total = len(per_scenario) or 1
    overall_rate = scenario_pass / total
    if overall_rate >= 0.85:
        overall = "pass"
    elif overall_rate >= 0.5:
        overall = "flaky"
    else:
        overall = "fail"

    dim_rates = {
        d: round(dim_pass[d] / dim_total[d], 3) if dim_total[d] else None for d in sorted(dim_total)
    }

    conclusion = {
        "overall": overall,
        "scenario_pass_rate": round(overall_rate, 3),
        "scenarios_passed": scenario_pass,
        "scenarios_total": len(per_scenario),
        "dimension_pass_rates": dim_rates,
        "per_scenario": per_scenario,
        "failure_themes": [{"theme": t, "count": c} for t, c in themes.most_common(12)],
        "manifest": {
            "run_id": manifest.get("run_id"),
            "tenant_id": manifest.get("tenant_id"),
            "country": manifest.get("country"),
        },
    }

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
        f"- Tenant: `{c.get('manifest', {}).get('tenant_id')}` · "
        f"Run: `{c.get('manifest', {}).get('run_id')}`",
        "",
        "## Dimension pass rates",
        "",
    ]
    for dim, rate in (c.get("dimension_pass_rates") or {}).items():
        lines.append(f"- `{dim}`: {rate}")
    lines += ["", "## Per scenario", ""]
    for p in c.get("per_scenario") or []:
        lines.append(
            f"- **{p['verdict']}** `{p['scenario_id']}` — turn pass rate {p['turn_pass_rate']} "
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
