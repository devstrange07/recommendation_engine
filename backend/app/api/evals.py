"""Eval harness API — catalog profile, scenarios, multi-turn runs."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.deps import get_tenant_id
from app.evals import scenario_author, scenario_gen
from app.evals.models import (
    GenerateScenariosRequest,
    ScenarioConfirmRequest,
    ScenarioDraftRequest,
    StartEvalRunRequest,
)
from app.evals.profile import generate_catalog_profile, load_catalog_profile
from app.evals.runner import get_live_events, get_run_state, list_run_dirs, load_run, start_run
from app.evals.scenario_store import delete_scenario, list_scenarios
from app.pipeline.paths import TenantPaths, safe_id

router = APIRouter(prefix="/evals", tags=["evals"])


def _require_safe_id(value: str) -> str:
    try:
        return safe_id(value)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/profile")
def get_profile(tenant_id: str = Depends(get_tenant_id)):
    profile = load_catalog_profile(tenant_id)
    if profile is None:
        return {"profile": None, "exists": False}
    return {"profile": profile, "exists": True}


@router.post("/profile/regenerate")
def regenerate_profile(tenant_id: str = Depends(get_tenant_id)):
    try:
        profile = generate_catalog_profile(tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"profile": profile, "exists": True}


@router.get("/scenarios")
def get_scenarios(tenant_id: str = Depends(get_tenant_id)):
    return {"scenarios": [s.model_dump(mode="json") for s in list_scenarios(tenant_id)]}


@router.post("/scenarios/generate")
def post_generate_scenarios(
    body: GenerateScenariosRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    scenarios = scenario_gen.generate_scenarios(
        tenant_id, count=body.count, replace=body.replace
    )
    return {"scenarios": [s.model_dump(mode="json") for s in scenarios]}


@router.post("/scenarios/draft")
def post_scenario_draft(
    body: ScenarioDraftRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        return scenario_author.create_draft(tenant_id, body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/scenarios/confirm")
def post_scenario_confirm(
    body: ScenarioConfirmRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        _require_safe_id(body.draft_id)
        sc = scenario_author.confirm_draft(tenant_id, body.draft_id, body.answers)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"scenario": sc.model_dump(mode="json")}


@router.delete("/scenarios/{scenario_id}")
def remove_scenario(scenario_id: str, tenant_id: str = Depends(get_tenant_id)):
    try:
        _require_safe_id(scenario_id)
    except HTTPException:
        raise
    ok = delete_scenario(tenant_id, scenario_id)
    if not ok:
        raise HTTPException(status_code=404, detail="scenario not found")
    return {"ok": True}


@router.post("/runs")
def post_start_run(
    body: StartEvalRunRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    try:
        run_id = start_run(
            tenant_id,
            scenario_ids=body.scenario_ids,
            country=body.country,
            max_turns=body.max_turns,
        )
    except ValueError as e:
        msg = str(e)
        if "already in progress" in msg.lower():
            raise HTTPException(status_code=409, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"run_id": run_id}


@router.get("/runs")
def get_runs(tenant_id: str = Depends(get_tenant_id)):
    return {"runs": list_run_dirs(tenant_id)}


@router.get("/runs/{run_id}")
def get_run(run_id: str, tenant_id: str = Depends(get_tenant_id)):
    rid = _require_safe_id(run_id)
    data = load_run(tenant_id, rid)
    if data is None:
        raise HTTPException(status_code=404, detail="run not found")
    state = get_run_state(tenant_id, rid)
    if state:
        data["status"] = state.get("status", data.get("status"))
        data["progress"] = state.get("progress")
    return data


@router.get("/runs/{run_id}/stream")
def stream_run(run_id: str, tenant_id: str = Depends(get_tenant_id)):
    rid = _require_safe_id(run_id)
    paths = TenantPaths.for_tenant(tenant_id)
    run_dir = paths.evals_runs / rid

    def events() -> Iterator[str]:
        # Replay backlog once so late subscribers catch earlier turns
        for snap in get_live_events(tenant_id, rid):
            yield f"data: {json.dumps(snap, ensure_ascii=False)}\n\n"

        last = ""
        for _ in range(3600):
            state = get_run_state(tenant_id, rid)
            progress_path = run_dir / "progress.json"
            payload: dict = {}
            if state:
                payload = {"status": state.get("status"), **(state.get("progress") or {})}
            elif progress_path.exists():
                try:
                    payload = json.loads(progress_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    payload = {"status": "unknown"}
            else:
                if (run_dir / "conclusion.json").exists():
                    payload = {"status": "done", "message": "Complete", "event": "run_done"}
                else:
                    payload = {"status": "pending", "message": "waiting"}

            text = json.dumps(payload, ensure_ascii=False)
            if text != last:
                last = text
                yield f"data: {text}\n\n"
            if payload.get("status") in ("done", "error"):
                break
            time.sleep(0.4)

    return StreamingResponse(events(), media_type="text/event-stream")
