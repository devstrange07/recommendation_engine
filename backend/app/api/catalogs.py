"""Server-backed catalog registry (list / create / rename)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.catalog_registry import create_catalog, list_catalogs, rename_catalog
from app.schemas import CatalogEntry, CreateCatalogRequest, RenameCatalogRequest

router = APIRouter(prefix="/catalogs", tags=["catalogs"])


@router.get("", response_model=list[CatalogEntry])
def get_catalogs():
    return [CatalogEntry.model_validate(e) for e in list_catalogs()]


@router.post("", response_model=CatalogEntry)
def post_catalog(body: CreateCatalogRequest):
    entry = create_catalog(body.title)
    return CatalogEntry.model_validate(entry)


@router.patch("/{catalog_id}", response_model=CatalogEntry)
def patch_catalog(catalog_id: str, body: RenameCatalogRequest):
    try:
        entry = rename_catalog(catalog_id, body.title)
    except ValueError as e:
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status, msg) from e
    return CatalogEntry.model_validate(entry)
