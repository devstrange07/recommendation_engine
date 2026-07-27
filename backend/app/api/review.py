"""Review queue endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_tenant_id
from app.pipeline.io_utils import ensure_data_dirs
from app.pipeline.review_store import load_queue, save_override
from app.schemas import OverrideAnswer, ReviewFlagItem

router = APIRouter()


@router.get("/review/queue", response_model=list[ReviewFlagItem])
def get_review_queue(tenant_id: str = Depends(get_tenant_id)):
    paths = ensure_data_dirs(tenant_id)
    return load_queue(paths)


@router.post("/review/override")
def post_override(answer: OverrideAnswer, tenant_id: str = Depends(get_tenant_id)):
    paths = ensure_data_dirs(tenant_id)
    save_override(paths, answer)
    return {"ok": True, "product_id": answer.product_id}


@router.get("/products/{product_id}")
def get_product(product_id: str, tenant_id: str = Depends(get_tenant_id)):
    paths = ensure_data_dirs(tenant_id)
    path = paths.canonical / f"{product_id}.json"
    if not path.exists():
        raise HTTPException(404, "product not found")
    import json

    return json.loads(path.read_text(encoding="utf-8"))
