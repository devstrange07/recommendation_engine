const BASE = "/api";

async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  tenantId?: string
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("X-Tenant-Id", tenantId ?? "demo");
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type ProductCard = {
  id: string;
  title: string;
  pitch: string;
  price_display: string;
  plan_names: string[];
};

export type DebugTrace = {
  turn_flow: string[];
  extracted_filters: Record<string, unknown> | null;
  previous_filters: Record<string, unknown> | null;
  qdrant_query: Record<string, unknown> | null;
  hits: Array<{
    id: string;
    dense_score: number | null;
    sparse_score: number | null;
    semantic_score: number | null;
    rrf_score: number | null;
    rrf_rank: number;
    payload_excerpt: Record<string, unknown>;
    review_pending: boolean;
  }>;
  fallback: {
    triggered: boolean;
    action: string | null;
    steps: Array<Record<string, unknown>>;
  };
  injected_prompt_block: string | null;
  tokens: Record<string, number>;
  latency_ms: Record<string, number>;
  reasoning_summary_understand?: string | null;
  reasoning_summary_final?: string | null;
};

export type ChatResponse = {
  reply: string;
  product_cards: ProductCard[];
  debug: DebugTrace;
};

export type ReviewFlagItem = {
  product_id: string;
  product_name: string | null;
  flag: {
    type: string;
    field: string;
    issue: string;
    options: string[];
    recommended: string | null;
  };
  recommended: string | null;
};

export type ProductListItem = {
  product_id: string;
  name: string;
  status: "indexed" | "flagged" | "failed" | "pending" | "processing";
  flags: string[];
};

export type ProductIngestResult = {
  product_id: string;
  name: string;
  status: ProductListItem["status"];
  flags: string[];
  error?: string | null;
};

export type IngestJobResponse = {
  tenant_id: string;
  products: ProductIngestResult[];
  pipeline_summary: string | null;
};

export type IngestValidateResponse = {
  valid: boolean;
  products: ProductIngestResult[];
  errors: string[];
};

export type CreatePriceRequest = {
  country: string;
  currency: string;
  amount: number;
};

export type CreatePlanRequest = {
  name: string;
  feature_text?: string;
  billing_period?: "one_time" | "monthly" | "annual";
  prices: CreatePriceRequest[];
};

export type CreateProductRequest = {
  name: string;
  description: string;
  category?: string;
  plans: CreatePlanRequest[];
};

export async function postChat(
  sessionId: string,
  country: string,
  messages: ChatMessage[],
  tenantId = "demo",
  catalogTitle?: string
): Promise<ChatResponse> {
  return apiFetch(
    "/chat",
    {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        country,
        messages,
        catalog_title: catalogTitle || undefined,
      }),
    },
    tenantId
  );
}

export async function getReviewQueue(tenantId = "demo"): Promise<ReviewFlagItem[]> {
  return apiFetch("/review/queue", {}, tenantId);
}

export async function postOverride(
  body: {
    product_id: string;
    field: string;
    value: string;
    flag_type?: string;
  },
  tenantId = "demo"
) {
  return apiFetch(
    "/review/override",
    { method: "POST", body: JSON.stringify(body) },
    tenantId
  );
}

export async function runPipeline(
  sync = true,
  tenantId = "demo"
): Promise<{ ok: boolean; summary?: string; message?: string }> {
  return apiFetch(`/pipeline/run?sync=${sync}`, { method: "POST" }, tenantId);
}

export async function getHealth(): Promise<{
  ok: boolean;
  openai_key_present: boolean;
  langsmith_key_present?: boolean;
  qdrant_reachable: boolean;
  chat_model?: string;
  chat_reasoning_effort?: string;
  embedding_model?: string;
  langsmith_project?: string;
}> {
  return apiFetch("/health");
}

export async function getPipelineStatus(tenantId = "demo"): Promise<{
  stage_counts: Record<string, number>;
  review_pending_count: number;
  last_run_summary: string | null;
}> {
  return apiFetch("/pipeline/status", {}, tenantId);
}

export async function getProduct(id: string, tenantId = "demo") {
  return apiFetch(`/products/${id}`, {}, tenantId);
}

export async function listCatalogProducts(tenantId: string): Promise<ProductListItem[]> {
  return apiFetch("/catalog/products", {}, tenantId);
}

export async function deleteCatalog(tenantId: string): Promise<{
  ok: boolean;
  tenant_id: string;
  collection: string;
  collection_deleted: boolean;
  tenant_deleted: boolean;
}> {
  return apiFetch("/catalog", { method: "DELETE" }, tenantId);
}

export type CatalogEntry = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  productCount?: number;
};

export async function listCatalogs(): Promise<CatalogEntry[]> {
  return apiFetch("/catalogs", {});
}

export async function createCatalog(title: string): Promise<CatalogEntry> {
  return apiFetch("/catalogs", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export async function renameCatalog(
  catalogId: string,
  title: string
): Promise<CatalogEntry> {
  return apiFetch(`/catalogs/${encodeURIComponent(catalogId)}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function createCatalogProduct(
  body: CreateProductRequest,
  tenantId: string
): Promise<IngestJobResponse> {
  return apiFetch(
    "/catalog/products",
    { method: "POST", body: JSON.stringify(body) },
    tenantId
  );
}

export async function ingestCatalogText(
  text: string,
  sourceName: string | undefined,
  tenantId: string
): Promise<IngestJobResponse> {
  return apiFetch(
    "/catalog/ingest/text",
    {
      method: "POST",
      body: JSON.stringify({ text, source_name: sourceName }),
    },
    tenantId
  );
}

export async function validateCatalogText(
  text: string,
  sourceName: string | undefined,
  tenantId: string
): Promise<IngestValidateResponse> {
  return apiFetch(
    "/catalog/ingest/validate",
    {
      method: "POST",
      body: JSON.stringify({ text, source_name: sourceName }),
    },
    tenantId
  );
}

export async function ingestCatalogFile(
  file: File,
  tenantId: string
): Promise<IngestJobResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch("/catalog/ingest/file", { method: "POST", body: form }, tenantId);
}

// ---------------------------------------------------------------------------
// Pipeline thought-stream (SSE over POST)
// ---------------------------------------------------------------------------

export type ProgressPhase =
  | "ingest"
  | "preprocess"
  | "normalize"
  | "merge"
  | "index"
  | "done";

export type ProgressEventType =
  | "phase_start"
  | "subtask"
  | "phase_done"
  | "error"
  | "done";

export type ProgressEvent = {
  type: ProgressEventType;
  phase: ProgressPhase;
  message: string;
  detail?: Record<string, unknown> | null;
  ts: string;
};

async function streamSse(
  path: string,
  init: RequestInit,
  tenantId: string,
  onEvent: (event: ProgressEvent) => void
): Promise<ProgressEvent> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("X-Tenant-Id", tenantId);
  headers.set("Accept", "text/event-stream");

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  if (!res.body) {
    throw new Error("No response body for SSE stream");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastDone: ProgressEvent | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const dataLine = part
        .split("\n")
        .map((l) => l.trimEnd())
        .find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      const raw = dataLine.slice(5).trim();
      if (!raw) continue;
      const event = JSON.parse(raw) as ProgressEvent;
      onEvent(event);
      if (event.type === "error") {
        throw new Error(event.message);
      }
      if (event.type === "done") {
        lastDone = event;
      }
    }
  }

  if (!lastDone) {
    throw new Error("Stream ended without a done event");
  }
  return lastDone;
}

export async function streamIngestText(
  text: string,
  sourceName: string | undefined,
  tenantId: string,
  onEvent: (event: ProgressEvent) => void
): Promise<IngestJobResponse> {
  const done = await streamSse(
    "/catalog/ingest/text/stream",
    {
      method: "POST",
      body: JSON.stringify({ text, source_name: sourceName }),
    },
    tenantId,
    onEvent
  );
  return done.detail as unknown as IngestJobResponse;
}

export async function streamCreateProduct(
  body: CreateProductRequest,
  tenantId: string,
  onEvent: (event: ProgressEvent) => void
): Promise<IngestJobResponse> {
  const done = await streamSse(
    "/catalog/products/stream",
    { method: "POST", body: JSON.stringify(body) },
    tenantId,
    onEvent
  );
  return done.detail as unknown as IngestJobResponse;
}

export async function streamIngestFile(
  file: File,
  tenantId: string,
  onEvent: (event: ProgressEvent) => void
): Promise<IngestJobResponse> {
  const form = new FormData();
  form.append("file", file);
  const done = await streamSse(
    "/catalog/ingest/file/stream",
    { method: "POST", body: form },
    tenantId,
    onEvent
  );
  return done.detail as unknown as IngestJobResponse;
}

export async function streamPipelineRun(
  tenantId: string,
  onEvent: (event: ProgressEvent) => void
): Promise<{ ok: boolean; summary?: string }> {
  const done = await streamSse(
    "/pipeline/run/stream",
    { method: "POST" },
    tenantId,
    onEvent
  );
  const detail = (done.detail || {}) as { ok?: boolean; summary?: string };
  return { ok: detail.ok !== false, summary: detail.summary };
}
