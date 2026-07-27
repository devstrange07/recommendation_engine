"""FastAPI dependencies."""

from fastapi import Header

from app.pipeline.paths import sanitize_tenant_id, DEMO_TENANT


def get_tenant_id(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")) -> str:
    return sanitize_tenant_id(x_tenant_id or DEMO_TENANT)
