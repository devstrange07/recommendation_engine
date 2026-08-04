"""Multi-turn eval suite runner."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.evals.conclude import build_conclusion
from app.evals.judge import build_retrieval_blob, default_judge_model, judge_turn, write_promptfoo_cases
from app.evals.models import EvalScenario
from app.evals.profile import load_catalog_profile, generate_catalog_profile
from app.evals.query_agent import next_user_turn
from app.evals.scenario_store import get_scenario, list_scenarios
from app.pipeline.paths import ensure_tenant_dirs
from app.rag.chat import run_chat_turn
from app.schemas import ChatMessage, ChatRequest

ProgressCb = Callable[[dict[str, Any]], None]

_run_lock = threading.Lock()
_runs: dict[str, dict[str, Any]] = {}


def get_run_state(tenant_id: str, run_id: str) -> dict[str, Any] | None:
    return _runs.get(f"{tenant_id}:{run_id}")


def list_run_dirs(tenant_id: str) -> list[dict[str, Any]]:
    paths = ensure_tenant_dirs(tenant_id)
    out: list[dict[str, Any]] = []
    if not paths.evals_runs.exists():
        return out
    for d in sorted(paths.evals_runs.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        manifest = {}
        mp = d / "manifest.json"
        if mp.exists():
            try:
                manifest = json.loads(mp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        conclusion = None
        cp = d / "conclusion.json"
        if cp.exists():
            try:
                conclusion = json.loads(cp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        out.append(
            {
                "run_id": d.name,
                "manifest": manifest,
                "conclusion": conclusion,
                "status": (_runs.get(f"{tenant_id}:{d.name}") or {}).get("status")
                or ("done" if conclusion else "unknown"),
            }
        )
    return out


def load_run(tenant_id: str, run_id: str) -> dict[str, Any] | None:
    paths = ensure_tenant_dirs(tenant_id)
    run_dir = paths.evals_runs / run_id
    if not run_dir.exists():
        return None
    manifest = {}
    if (run_dir / "manifest.json").exists():
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    conclusion = None
    if (run_dir / "conclusion.json").exists():
        conclusion = json.loads((run_dir / "conclusion.json").read_text(encoding="utf-8"))
    conclusion_md = None
    if (run_dir / "conclusion.md").exists():
        conclusion_md = (run_dir / "conclusion.md").read_text(encoding="utf-8")
    scenarios: dict[str, list[dict]] = {}
    scen_dir = run_dir / "scenarios"
    if scen_dir.exists():
        for f in scen_dir.glob("*.jsonl"):
            turns = []
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    turns.append(json.loads(line))
            scenarios[f.stem] = turns
    state = _runs.get(f"{tenant_id}:{run_id}") or {}
    return {
        "run_id": run_id,
        "manifest": manifest,
        "conclusion": conclusion,
        "conclusion_md": conclusion_md,
        "scenarios": scenarios,
        "status": state.get("status") or ("done" if conclusion else "unknown"),
        "progress": state.get("progress"),
    }


def start_run(
    tenant_id: str,
    *,
    scenario_ids: list[str] | None = None,
    country: str = "IN",
    max_turns: int | None = None,
    catalog_title: str | None = None,
) -> str:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"{tenant_id}:{run_id}"
    with _run_lock:
        _runs[key] = {
            "status": "pending",
            "progress": {"message": "starting", "event": "run_pending"},
            "live_events": [],
        }

    def _target() -> None:
        try:
            _execute_run(
                tenant_id,
                run_id,
                scenario_ids=scenario_ids,
                country=country,
                max_turns=max_turns,
                catalog_title=catalog_title,
            )
        except Exception as e:
            with _run_lock:
                cur = _runs.get(key) or {}
                _runs[key] = {
                    "status": "error",
                    "progress": {"message": str(e), "event": "error"},
                    "live_events": list(cur.get("live_events") or []),
                }
            paths = ensure_tenant_dirs(tenant_id)
            err_dir = paths.evals_runs / run_id
            err_dir.mkdir(parents=True, exist_ok=True)
            (err_dir / "error.txt").write_text(str(e), encoding="utf-8")

    threading.Thread(target=_target, daemon=True).start()
    return run_id


_LIVE_EVENT_CAP = 50
_LIVE_EVENT_TYPES = frozenset(
    {"scenario_start", "turn_start", "turn_complete", "turn_judged", "scenario_done"}
)


def _compact_filters(filters: dict[str, Any] | None) -> dict[str, Any] | None:
    if not filters:
        return None
    keys = (
        "semantic_query",
        "category_path",
        "price_max",
        "brand",
        "exclude_terms",
        "attribute_filters",
        "use_case_tags",
        "kind",
    )
    return {k: filters[k] for k in keys if filters.get(k) not in (None, [], "")}


def _compact_hits(hits: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in hits[:limit]:
        excerpt = h.get("payload_excerpt") or {}
        out.append(
            {
                "id": h.get("id"),
                "title": excerpt.get("title") or excerpt.get("name"),
                "category_path": excerpt.get("category_path"),
                "rrf_rank": h.get("rrf_rank"),
            }
        )
    return out


def _set_progress(tenant_id: str, run_id: str, **kwargs: Any) -> None:
    key = f"{tenant_id}:{run_id}"
    with _run_lock:
        cur = _runs.get(key) or {}
        progress = dict(cur.get("progress") or {})
        # Drop previous turn_payload unless this event supplies a new one
        if "turn_payload" not in kwargs:
            progress.pop("turn_payload", None)
        progress.update(kwargs)
        live_events = list(cur.get("live_events") or [])
        event_name = kwargs.get("event")
        if event_name in _LIVE_EVENT_TYPES:
            snap = {
                "event": event_name,
                "status": kwargs.get("status") or cur.get("status") or "running",
                "message": progress.get("message"),
                "scenario_id": progress.get("scenario_id"),
                "turn": progress.get("turn"),
                "turn_payload": progress.get("turn_payload"),
                "scenario_title": progress.get("scenario_title"),
                "scenario_index": progress.get("scenario_index"),
                "scenario_total": progress.get("scenario_total"),
            }
            live_events.append(snap)
            if len(live_events) > _LIVE_EVENT_CAP:
                live_events = live_events[-_LIVE_EVENT_CAP:]
        status = kwargs.get("status") or cur.get("status") or "running"
        _runs[key] = {
            "status": status,
            "progress": progress,
            "live_events": live_events,
        }
        paths = ensure_tenant_dirs(tenant_id)
        run_dir = paths.evals_runs / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "progress.json").write_text(
            json.dumps({"status": status, **progress}, ensure_ascii=False),
            encoding="utf-8",
        )


def get_live_events(tenant_id: str, run_id: str) -> list[dict[str, Any]]:
    state = _runs.get(f"{tenant_id}:{run_id}") or {}
    return list(state.get("live_events") or [])


def _execute_run(
    tenant_id: str,
    run_id: str,
    *,
    scenario_ids: list[str] | None,
    country: str,
    max_turns: int | None,
    catalog_title: str | None,
) -> None:
    paths = ensure_tenant_dirs(tenant_id)
    run_dir = paths.evals_runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "scenarios").mkdir(exist_ok=True)

    profile = load_catalog_profile(tenant_id)
    if profile is None:
        _set_progress(tenant_id, run_id, status="running", message="Generating catalog profile")
        profile = generate_catalog_profile(tenant_id)

    all_scenarios = list_scenarios(tenant_id)
    if scenario_ids:
        scenarios = [s for s in all_scenarios if s.id in scenario_ids]
        # also allow lookup of missing by id
        for sid in scenario_ids:
            if not any(s.id == sid for s in scenarios):
                sc = get_scenario(tenant_id, sid)
                if sc:
                    scenarios.append(sc)
    else:
        scenarios = all_scenarios

    if not scenarios:
        raise ValueError("No scenarios to run — generate or author scenarios first")

    import hashlib

    profile_raw = paths.catalog_profile.read_bytes() if paths.catalog_profile.exists() else b""
    manifest = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "country": country,
        "max_turns_override": max_turns,
        "scenario_ids": [s.id for s in scenarios],
        "judge_model": default_judge_model(),
        "profile_sha256": hashlib.sha256(profile_raw).hexdigest()[:16],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _set_progress(tenant_id, run_id, status="running", message="Running scenarios", event="run_start")

    scenario_results: list[dict[str, Any]] = []
    pf_cases: list[dict[str, Any]] = []
    total = len(scenarios)

    for i, sc in enumerate(scenarios):
        cap = max_turns or sc.max_turns or 6
        result = _run_scenario(
            tenant_id=tenant_id,
            run_id=run_id,
            run_dir=run_dir,
            scenario=sc,
            profile=profile,
            country=country,
            max_turns=cap,
            catalog_title=catalog_title,
            pf_cases=pf_cases,
            scenario_index=i + 1,
            scenario_total=total,
        )
        scenario_results.append(result)

    write_promptfoo_cases(run_dir, pf_cases)
    conclusion = build_conclusion(run_dir, manifest, scenario_results)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["overall"] = conclusion.get("overall")
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _set_progress(
        tenant_id,
        run_id,
        status="done",
        message="Complete",
        overall=conclusion.get("overall"),
        event="run_done",
    )


def _hit_debug_dicts(debug_hits: list) -> list[dict[str, Any]]:
    out = []
    for h in debug_hits:
        if hasattr(h, "model_dump"):
            out.append(h.model_dump())
        elif isinstance(h, dict):
            out.append(h)
    return out


def _run_scenario(
    *,
    tenant_id: str,
    run_id: str,
    run_dir: Path,
    scenario: EvalScenario,
    profile: dict[str, Any] | None,
    country: str,
    max_turns: int,
    catalog_title: str | None,
    pf_cases: list[dict[str, Any]],
    scenario_index: int = 1,
    scenario_total: int = 1,
) -> dict[str, Any]:
    session_id = f"eval-{run_id}-{scenario.id}"
    messages: list[dict[str, str]] = []
    turns_out: list[dict[str, Any]] = []
    last_retrieval: dict[str, Any] | None = None
    jsonl = run_dir / "scenarios" / f"{scenario.id}.jsonl"

    _set_progress(
        tenant_id,
        run_id,
        status="running",
        event="scenario_start",
        message=f"Starting {scenario.id}",
        scenario_id=scenario.id,
        scenario_title=scenario.title,
        scenario_index=scenario_index,
        scenario_total=scenario_total,
        turn=None,
    )

    for turn_idx in range(1, max_turns + 1):
        _set_progress(
            tenant_id,
            run_id,
            status="running",
            event="turn_start",
            message=f"{scenario.id} turn {turn_idx}",
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            scenario_index=scenario_index,
            scenario_total=scenario_total,
            turn=turn_idx,
        )
        agent = next_user_turn(
            scenario=scenario,
            profile=profile,
            messages=messages,
            last_retrieval=last_retrieval,
            turn_index=turn_idx,
        )
        # If agent says done before sending a message and we already have turns, stop
        if agent.goal_met and turns_out:
            break

        user_msg = agent.user_message.strip()
        if not user_msg:
            break

        messages.append({"role": "user", "content": user_msg})
        body = ChatRequest(
            session_id=session_id,
            country=country,
            messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages],  # type: ignore[arg-type]
            catalog_title=catalog_title,
        )
        resp = run_chat_turn(body, tenant_id=tenant_id)
        messages.append({"role": "assistant", "content": resp.reply})

        filters = resp.debug.extracted_filters
        hits = _hit_debug_dicts(resp.debug.hits)
        fallback = resp.debug.fallback.model_dump() if resp.debug.fallback else None
        last_retrieval = {
            "extracted_filters": filters,
            "hit_ids": [h.get("id") for h in hits],
            "hit_titles": [
                (h.get("payload_excerpt") or {}).get("title") for h in hits[:5]
            ],
            "fallback": fallback,
        }

        turn_payload = {
            "user_message": user_msg,
            "assistant_reply": (resp.reply or "")[:800],
            "agent_rationale": agent.rationale,
            "searched": filters is not None,
            "extracted_filters": _compact_filters(filters if isinstance(filters, dict) else None),
            "hits": _compact_hits(hits),
            "fallback": {
                "triggered": bool((fallback or {}).get("triggered")),
                "action": (fallback or {}).get("action"),
            },
        }
        _set_progress(
            tenant_id,
            run_id,
            status="running",
            event="turn_complete",
            message=f"{scenario.id} turn {turn_idx} retrieved",
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            scenario_index=scenario_index,
            scenario_total=scenario_total,
            turn=turn_idx,
            turn_payload=turn_payload,
        )

        blob = build_retrieval_blob(
            scenario=scenario.model_dump(mode="json"),
            soft_expectations=scenario.soft_expectations.model_dump(),
            user_message=user_msg,
            extracted_filters=filters,
            hits=hits,
            fallback=fallback,
        )
        _set_progress(
            tenant_id,
            run_id,
            status="running",
            event="judging",
            message=f"Judging {scenario.id} turn {turn_idx}",
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            turn=turn_idx,
        )
        rubric = judge_turn(blob)
        rubric_dump = rubric.model_dump(by_alias=True)
        dim_summary = [
            {
                "dimension": s.get("dimension"),
                "pass": s.get("pass"),
            }
            for s in (rubric_dump.get("scores") or [])
        ]
        judged_payload = {
            **turn_payload,
            "rubric_pass": rubric_dump.get("pass"),
            "rubric_reasoning": (rubric_dump.get("reasoning") or "")[:400],
            "dimension_summary": dim_summary,
        }
        _set_progress(
            tenant_id,
            run_id,
            status="running",
            event="turn_judged",
            message=f"Judged {scenario.id} turn {turn_idx}",
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            scenario_index=scenario_index,
            scenario_total=scenario_total,
            turn=turn_idx,
            turn_payload=judged_payload,
        )

        turn_rec = {
            "turn": turn_idx,
            "user_message": user_msg,
            "agent_rationale": agent.rationale,
            "goal_met_signal": agent.goal_met,
            "assistant_reply": resp.reply[:500],
            "extracted_filters": filters,
            "hits": [{"id": h.get("id"), "rrf_rank": h.get("rrf_rank"), "payload_excerpt": h.get("payload_excerpt")} for h in hits],
            "fallback": fallback,
            "rubric": rubric_dump,
        }
        turns_out.append(turn_rec)
        with jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(turn_rec, ensure_ascii=False) + "\n")

        pf_cases.append(
            {
                "scenario_id": scenario.id,
                "turn": turn_idx,
                "blob": blob,
            }
        )

        if agent.goal_met:
            break

    # Hard fail if must_use_search and never searched
    searched = any(t.get("extracted_filters") for t in turns_out)
    if scenario.soft_expectations.must_use_search and not searched and turns_out:
        for t in turns_out:
            rub = t.get("rubric") or {}
            rub["pass"] = False
            rub["reasoning"] = (rub.get("reasoning") or "") + " | must_use_search but no search_products"
            t["rubric"] = rub
        # rewrite jsonl
        with jsonl.open("w", encoding="utf-8") as f:
            for t in turns_out:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

    _set_progress(
        tenant_id,
        run_id,
        status="running",
        event="scenario_done",
        message=f"Finished {scenario.id}",
        scenario_id=scenario.id,
        scenario_title=scenario.title,
        scenario_index=scenario_index,
        scenario_total=scenario_total,
    )

    return {
        "scenario_id": scenario.id,
        "title": scenario.title,
        "soft_expectations": scenario.soft_expectations.model_dump(),
        "turns": turns_out,
    }
