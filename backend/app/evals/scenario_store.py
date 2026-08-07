"""Load/save eval scenario YAML files."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.evals.models import EvalScenario
from app.pipeline.paths import TenantPaths, ensure_tenant_dirs, safe_id


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (s or "scenario")[:64]


def scenario_path(paths: TenantPaths, scenario_id: str) -> Path:
    safe = safe_id(_slug(scenario_id))
    return paths.evals_scenarios / f"{safe}.yaml"


def list_scenarios(tenant_id: str) -> list[EvalScenario]:
    paths = ensure_tenant_dirs(tenant_id)
    out: list[EvalScenario] = []
    for p in sorted(paths.evals_scenarios.glob("*.yaml")):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            out.append(EvalScenario.model_validate(data))
        except Exception:
            continue
    return out


def get_scenario(tenant_id: str, scenario_id: str) -> EvalScenario | None:
    paths = TenantPaths.for_tenant(tenant_id)
    p = scenario_path(paths, scenario_id)
    if not p.exists():
        # try exact filename match
        for f in paths.evals_scenarios.glob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                sc = EvalScenario.model_validate(data)
                if sc.id == scenario_id:
                    return sc
            except Exception:
                continue
        return None
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return EvalScenario.model_validate(data)


def save_scenario(tenant_id: str, scenario: EvalScenario) -> Path:
    paths = ensure_tenant_dirs(tenant_id)
    scenario.id = _slug(scenario.id)
    path = scenario_path(paths, scenario.id)
    path.write_text(
        yaml.safe_dump(scenario.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def delete_scenario(tenant_id: str, scenario_id: str) -> bool:
    paths = TenantPaths.for_tenant(tenant_id)
    p = scenario_path(paths, scenario_id)
    if p.exists():
        p.unlink()
        return True
    for f in paths.evals_scenarios.glob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            if data.get("id") == scenario_id:
                f.unlink()
                return True
        except Exception:
            continue
    return False
