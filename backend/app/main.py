"""FastAPI entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import QdrantClient

from app.api import admin, catalog, chat, review
from app.config import get_settings, langsmith_key_present
from app.openai_client import configure_langsmith
from app.pipeline.io_utils import ensure_data_dirs
from app.pipeline.paths import DEMO_TENANT, TenantPaths, migrate_legacy_to_demo
from app.pipeline.s4_index import get_qdrant

app = FastAPI(title="Prism", version="0.1.0")


def ensure_demo_indexed() -> None:
    """Re-index demo canonical products if Qdrant collection is missing."""
    paths = TenantPaths.for_tenant(DEMO_TENANT)
    if not paths.canonical.exists() or not any(paths.canonical.glob("*.json")):
        return
    client = get_qdrant()
    existing = {c.name for c in client.get_collections().collections}
    if paths.collection in existing:
        return
    from app.pipeline import s4_index

    print(f"INFO: indexing demo catalog into {paths.collection}")
    s4_index.run(DEMO_TENANT, force_all=True)


# Configure LangSmith env early so wrapped OpenAI clients pick it up
configure_langsmith()
migrate_legacy_to_demo()
ensure_data_dirs("demo")
ensure_demo_indexed()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, tags=["chat"])
app.include_router(review.router, tags=["review"])
app.include_router(admin.router, tags=["admin"])
app.include_router(catalog.router)


@app.get("/health")
def health():
    settings = get_settings()
    qdrant_ok = False
    try:
        client = QdrantClient(url=settings.qdrant_url, timeout=3, check_compatibility=False)
        client.get_collections()
        qdrant_ok = True
    except Exception:
        qdrant_ok = False
    key = (settings.openai_api_key or "").strip()
    key_present = bool(key) and key != "sk-your-key-here"
    return {
        "ok": True,
        "openai_key_present": key_present,
        "langsmith_key_present": langsmith_key_present(settings),
        "qdrant_reachable": qdrant_ok,
        "chat_model": settings.chat_model,
        "chat_reasoning_effort": settings.chat_reasoning_effort,
        "embedding_model": settings.embedding_model,
        "langsmith_project": settings.langsmith_project,
    }
