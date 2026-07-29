"""App settings loaded from env / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root = product-rag/ (parent of backend/)
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
VOCAB_DIR = REPO_ROOT / "vocab"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    deepseek_api_key: str = ""
    # openai | deepseek — selects chat/pipeline LLM; embeddings always use OpenAI
    chat_provider: str = "openai"
    qdrant_url: str = "http://localhost:6333"
    chat_model: str = "gpt-5.4-mini"
    chat_reasoning_effort: str = "medium"
    embedding_model: str = "text-embedding-3-small"
    qdrant_collection: str = "products"
    data_dir: Path = DATA_DIR
    vocab_dir: Path = VOCAB_DIR

    langsmith_api_key: str = ""
    langsmith_tracing: bool = True
    langsmith_project: str = "prism"


def langsmith_key_present(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    key = (s.langsmith_api_key or "").strip()
    return bool(key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
