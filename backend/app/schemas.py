"""All Pydantic models — single source of truth for the app."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Raw (synthetic generator — intentionally messy)
# ---------------------------------------------------------------------------

class RawPriceList(BaseModel):
    name: str
    country: str
    currency: str
    amount: float
    discount: float | None = None
    discount_strategy: str | None = None


class RawPlan(BaseModel):
    id: str
    name: str
    feature_text: str | None = None
    price_lists: list[RawPriceList]
    billing_period: str | None = None  # messy free text in raw


class RawProduct(BaseModel):
    id: str
    name: str
    category: str | None = None
    unit: str | None = None
    kb_article: str | None = None
    description: str
    plans: list[RawPlan]
    updated_at: str


# ---------------------------------------------------------------------------
# Staged (after deterministic pre-processing)
# ---------------------------------------------------------------------------

class StagedPrice(BaseModel):
    country: str  # ISO-3166 alpha-2
    currency: str  # ISO-4217
    amount: float
    discounted_amount: float | None = None


class StagedPlan(BaseModel):
    id: str
    name: str
    feature_text: str | None = None
    billing_period: Literal["one_time", "monthly", "annual"] | None = None
    prices: list[StagedPrice]


class StagedProduct(BaseModel):
    id: str
    name: str
    category_raw: str | None = None
    description_text: str
    unit: str | None = None
    kb_article: str | None = None
    plans: list[StagedPlan]
    price_min: dict[str, float]
    price_max: dict[str, float]
    content_hash: str
    needs_normalization: bool


# ---------------------------------------------------------------------------
# Normalization (LLM structured output)
# ---------------------------------------------------------------------------

FlagType = Literal[
    "ambiguous_attribute",
    "contradiction",
    "missing_required",
    "suspected_duplicate",
    "cant_categorize",
    "plans_indistinguishable",
]


class Flag(BaseModel):
    type: FlagType
    field: str
    issue: str
    options: list[str]
    recommended: str | None = None


class Normalized(BaseModel):
    clean_description: str
    short_pitch: str
    category_path: str
    use_case_tags: list[str]
    target_audience: list[str]
    aliases: list[str]
    plan_features: dict[str, list[str]]


class NormalizationRecord(BaseModel):
    product_id: str
    schema_version: int = 1
    normalized: Normalized
    confidence: float
    flags: list[Flag] = Field(default_factory=list)


# OpenAI structured-output wire types (no free-form dicts — strict schema forbids them)
class PlanFeatureEntry(BaseModel):
    plan_id: str
    features: list[str]


class NormalizedLLM(BaseModel):
    clean_description: str
    short_pitch: str
    category_path: str
    use_case_tags: list[str]
    target_audience: list[str]
    aliases: list[str]
    plan_features: list[PlanFeatureEntry]


class NormalizationRecordLLM(BaseModel):
    product_id: str
    schema_version: int = 1
    normalized: NormalizedLLM
    confidence: float
    flags: list[Flag] = Field(default_factory=list)


class NormalizationBatchResponse(BaseModel):
    records: list[NormalizationRecordLLM]


# ---------------------------------------------------------------------------
# Canonical (feeds embedding + Qdrant payload)
# ---------------------------------------------------------------------------

class Offering(BaseModel):
    id: str
    name: str
    features: list[str]
    billing_period: Literal["one_time", "monthly", "annual"] | None = None
    prices: list[StagedPrice]


class CanonicalProduct(BaseModel):
    id: str
    kind: Literal["service", "subscription", "digital_good"] = "service"
    title: str
    brand_or_provider: str | None = None
    category_path: str
    clean_description: str
    short_pitch: str
    use_case_tags: list[str]
    target_audience: list[str]
    aliases: list[str]
    price_min: dict[str, float]
    price_max: dict[str, float]
    availability: Literal["available", "unavailable"] = "available"
    status: Literal["active", "retired"] = "active"
    offerings: list[Offering]
    service_details: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    review_pending: bool = False
    schema_version: int = 1


# ---------------------------------------------------------------------------
# Search / Chat API
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    semantic_query: str
    category_path: str | None = None
    use_case_tags: list[str] = Field(default_factory=list)
    target_audience: list[str] = Field(default_factory=list)
    price_max: float | None = None
    billing_period: str | None = None
    top_k: int = 8


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    session_id: str
    country: str = "IN"
    messages: list[ChatMessage]
    catalog_title: str | None = None


class ProductCard(BaseModel):
    id: str
    title: str
    pitch: str
    price_display: str
    plan_names: list[str] = Field(default_factory=list)


class HitDebug(BaseModel):
    id: str
    dense_score: float | None = None
    sparse_score: float | None = None
    rrf_rank: int
    payload_excerpt: dict[str, Any] = Field(default_factory=dict)
    review_pending: bool = False


class FallbackDebug(BaseModel):
    triggered: bool = False
    action: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)


class DebugTrace(BaseModel):
    turn_flow: list[str] = Field(default_factory=list)
    extracted_filters: dict[str, Any] | None = None
    previous_filters: dict[str, Any] | None = None
    qdrant_query: dict[str, Any] | None = None
    hits: list[HitDebug] = Field(default_factory=list)
    fallback: FallbackDebug = Field(default_factory=FallbackDebug)
    injected_prompt_block: str | None = None
    tokens: dict[str, int] = Field(default_factory=dict)
    latency_ms: dict[str, float] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    reply: str
    product_cards: list[ProductCard] = Field(default_factory=list)
    debug: DebugTrace = Field(default_factory=DebugTrace)


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

class ReviewFlagItem(BaseModel):
    product_id: str
    product_name: str | None = None
    flag: Flag
    recommended: str | None = None


class OverrideAnswer(BaseModel):
    product_id: str
    field: str
    value: str
    flag_type: str | None = None


class PipelineStatus(BaseModel):
    stage_counts: dict[str, int] = Field(default_factory=dict)
    review_pending_count: int = 0
    last_run_summary: str | None = None


# ---------------------------------------------------------------------------
# Catalog ingest
# ---------------------------------------------------------------------------

class CreatePriceRequest(BaseModel):
    country: str
    currency: str
    amount: float


class CreatePlanRequest(BaseModel):
    name: str
    feature_text: str | None = None
    billing_period: Literal["one_time", "monthly", "annual"] | None = None
    prices: list[CreatePriceRequest] = Field(min_length=1)


class CreateProductRequest(BaseModel):
    name: str
    description: str
    category: str | None = None
    plans: list[CreatePlanRequest] = Field(min_length=1)


class ProductIngestResult(BaseModel):
    product_id: str
    name: str
    status: Literal["indexed", "flagged", "failed", "pending", "processing"]
    flags: list[str] = Field(default_factory=list)
    error: str | None = None


class IngestJobResponse(BaseModel):
    tenant_id: str
    products: list[ProductIngestResult]
    pipeline_summary: str | None = None


class ProductListItem(BaseModel):
    product_id: str
    name: str
    status: Literal["indexed", "flagged", "failed", "pending", "processing"]
    flags: list[str] = Field(default_factory=list)


class IngestValidateResponse(BaseModel):
    valid: bool
    products: list[ProductIngestResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class IngestTextRequest(BaseModel):
    text: str
    source_name: str | None = None


# ---------------------------------------------------------------------------
# Pipeline progress (SSE thought-stream)
# ---------------------------------------------------------------------------

ProgressEventType = Literal["phase_start", "subtask", "phase_done", "error", "done"]
ProgressPhase = Literal[
    "ingest", "preprocess", "normalize", "merge", "index", "done"
]


class ProgressEvent(BaseModel):
    type: ProgressEventType
    phase: ProgressPhase
    message: str
    detail: dict[str, Any] | None = None
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
