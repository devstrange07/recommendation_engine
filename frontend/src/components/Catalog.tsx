import { useEffect, useRef, useState, type DragEvent } from "react";
import {
  CreatePlanRequest,
  CreateProductRequest,
  IngestJobResponse,
  IngestValidateResponse,
  ProductListItem,
  ProgressEvent,
  listCatalogProducts,
  streamCreateProduct,
  streamIngestFile,
  streamIngestText,
  validateCatalogText,
} from "../api";
import { DEMO_CATALOG_ID } from "../hooks/useCatalogs";
import BentoGrid from "./BentoGrid";
import BentoTile from "./BentoTile";
import PipelineThoughtStream from "./PipelineThoughtStream";

type Tab = "upload" | "form" | "json";

type Props = {
  tenantId: string;
  title: string;
  onTryInChat: (productName: string) => void;
  onCatalogReady?: () => void;
  onGoToChat?: () => void;
  onNewCatalog?: () => void;
};

const EMPTY_PLAN = (): CreatePlanRequest => ({
  name: "Standard",
  feature_text: "",
  billing_period: "monthly",
  prices: [{ country: "IN", currency: "INR", amount: 999 }],
});

const EXAMPLE_JSON = `{
  "name": "SalonBook Pro",
  "description": "Online appointment scheduling for salons and spas.",
  "category": "Scheduling",
  "plans": [
    {
      "name": "Starter",
      "feature_text": "Online booking, SMS reminders",
      "billing_period": "monthly",
      "prices": [{ "country": "IN", "currency": "INR", "amount": 1499 }]
    }
  ]
}`;

const ACCEPT = ".json,.jsonl,.txt,.md,.csv";

export default function Catalog({
  tenantId,
  title,
  onTryInChat,
  onCatalogReady,
  onGoToChat,
  onNewCatalog,
}: Props) {
  const isDemo = tenantId === DEMO_CATALOG_ID;
  const [tab, setTab] = useState<Tab>("upload");
  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<IngestJobResponse | null>(null);
  const [validation, setValidation] = useState<IngestValidateResponse | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [streamEvents, setStreamEvents] = useState<ProgressEvent[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [plans, setPlans] = useState<CreatePlanRequest[]>([EMPTY_PLAN()]);

  const [jsonText, setJsonText] = useState(EXAMPLE_JSON);
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  async function refresh() {
    try {
      const list = await listCatalogProducts(tenantId);
      setProducts(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    setProducts([]);
    setLastResult(null);
    setValidation(null);
    setError(null);
    setStreamEvents([]);
    setStreamError(null);
    setStreaming(false);
    refresh();
  }, [tenantId]);

  function updatePlan(i: number, patch: Partial<CreatePlanRequest>) {
    setPlans((prev) => prev.map((p, idx) => (idx === i ? { ...p, ...patch } : p)));
  }

  function updatePrice(planIdx: number, priceIdx: number, field: string, value: string | number) {
    setPlans((prev) =>
      prev.map((p, i) => {
        if (i !== planIdx) return p;
        const prices = p.prices.map((pr, j) =>
          j === priceIdx ? { ...pr, [field]: value } : pr
        );
        return { ...p, prices };
      })
    );
  }

  function afterIngest(res: IngestJobResponse) {
    setLastResult(res);
    onCatalogReady?.();
  }

  function beginStream() {
    setBusy(true);
    setStreaming(true);
    setError(null);
    setStreamError(null);
    setStreamEvents([]);
  }

  function endStream() {
    setBusy(false);
    setStreaming(false);
  }

  function onStreamEvent(ev: ProgressEvent) {
    setStreamEvents((prev) => [...prev, ev]);
  }

  async function submitForm() {
    if (isDemo) return;
    beginStream();
    const body: CreateProductRequest = {
      name: name.trim(),
      description: description.trim(),
      category: category.trim() || undefined,
      plans,
    };
    try {
      const res = await streamCreateProduct(body, tenantId, onStreamEvent);
      afterIngest(res);
      await refresh();
      setName("");
      setDescription("");
      setCategory("");
      setPlans([EMPTY_PLAN()]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setStreamError(msg);
    } finally {
      endStream();
    }
  }

  async function validateJson() {
    if (isDemo) return;
    setBusy(true);
    setError(null);
    try {
      const res = await validateCatalogText(jsonText, "paste.json", tenantId);
      setValidation(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function importJson() {
    if (isDemo) return;
    beginStream();
    try {
      const res = await streamIngestText(jsonText, "paste.json", tenantId, onStreamEvent);
      afterIngest(res);
      setValidation(null);
      await refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setStreamError(msg);
    } finally {
      endStream();
    }
  }

  async function ingestFile(file: File) {
    if (isDemo) return;
    beginStream();
    try {
      const res = await streamIngestFile(file, tenantId, onStreamEvent);
      afterIngest(res);
      setUploadFile(null);
      await refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setStreamError(msg);
    } finally {
      endStream();
    }
  }

  async function submitUpload() {
    if (!uploadFile) return;
    await ingestFile(uploadFile);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (isDemo) return;
    const file = e.dataTransfer.files?.[0];
    if (file) {
      setUploadFile(file);
      void ingestFile(file);
    }
  }

  return (
    <BentoGrid layout="review">
      <BentoTile span="stat" title={`${title} · ${tenantId}`}>
        <div className="catalog-intro">
          {isDemo ? (
            <>
              Demo catalog is read-only sample data. Create a new catalog to upload or paste your
              own JSON.
              {onNewCatalog && (
                <div className="option-row" style={{ marginTop: "0.75rem" }}>
                  <button type="button" className="primary" onClick={onNewCatalog}>
                    New catalog
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              Drop a file or paste JSON to index products into this catalog. Chat and search use
              products from the catalog selected in the top bar.
            </>
          )}
        </div>
      </BentoTile>

      <BentoTile span="queue" title="Add products">
        {isDemo ? (
          <div className="empty">
            Switch to a user catalog or create one to add products.
            {onNewCatalog && (
              <div className="option-row" style={{ marginTop: "0.75rem" }}>
                <button type="button" className="primary" onClick={onNewCatalog}>
                  New catalog
                </button>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="catalog-tabs">
              {(["upload", "form", "json"] as Tab[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  className={tab === t ? "active" : ""}
                  onClick={() => setTab(t)}
                >
                  {t === "form" ? "Form" : t === "json" ? "Paste JSON" : "Upload"}
                </button>
              ))}
            </div>

            {tab === "upload" && (
              <div className="catalog-form">
                <div
                  className={`catalog-dropzone ${dragOver ? "catalog-dropzone--active" : ""}`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={onDrop}
                  onClick={() => fileInputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
                  }}
                >
                  <strong>Drop a catalog file here</strong>
                  <p className="catalog-hint">
                    or click to browse · .json, .jsonl, .txt, .md, .csv (max 2MB)
                  </p>
                  {uploadFile && !busy && (
                    <p className="catalog-dropzone__file">{uploadFile.name}</p>
                  )}
                  {busy && <p className="catalog-dropzone__file">Processing…</p>}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPT}
                  hidden
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    setUploadFile(f);
                    if (f) void ingestFile(f);
                  }}
                />
                {uploadFile && (
                  <div className="option-row">
                    <button
                      type="button"
                      className="primary"
                      disabled={busy}
                      onClick={submitUpload}
                    >
                      {busy ? "Processing…" : "Upload & index"}
                    </button>
                  </div>
                )}
              </div>
            )}

            {tab === "form" && (
              <div className="catalog-form">
                <label>
                  Name
                  <input value={name} onChange={(e) => setName(e.target.value)} />
                </label>
                <label>
                  Description
                  <textarea
                    rows={3}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </label>
                <label>
                  Category (optional)
                  <input value={category} onChange={(e) => setCategory(e.target.value)} />
                </label>
                {plans.map((plan, pi) => (
                  <div key={pi} className="review-card">
                    <strong>Plan {pi + 1}</strong>
                    <input
                      placeholder="Plan name"
                      value={plan.name}
                      onChange={(e) => updatePlan(pi, { name: e.target.value })}
                    />
                    <input
                      placeholder="Features"
                      value={plan.feature_text || ""}
                      onChange={(e) => updatePlan(pi, { feature_text: e.target.value })}
                    />
                    <select
                      value={plan.billing_period || "monthly"}
                      onChange={(e) =>
                        updatePlan(pi, {
                          billing_period: e.target.value as CreatePlanRequest["billing_period"],
                        })
                      }
                    >
                      <option value="monthly">Monthly</option>
                      <option value="annual">Annual</option>
                      <option value="one_time">One-time</option>
                    </select>
                    {plan.prices.map((price, pri) => (
                      <div key={pri} className="option-row">
                        <select
                          value={price.country}
                          onChange={(e) => updatePrice(pi, pri, "country", e.target.value)}
                        >
                          <option value="IN">IN</option>
                          <option value="US">US</option>
                          <option value="GB">GB</option>
                        </select>
                        <input
                          placeholder="Currency"
                          value={price.currency}
                          onChange={(e) => updatePrice(pi, pri, "currency", e.target.value)}
                        />
                        <input
                          type="number"
                          placeholder="Amount"
                          value={price.amount}
                          onChange={(e) =>
                            updatePrice(pi, pri, "amount", Number(e.target.value))
                          }
                        />
                      </div>
                    ))}
                  </div>
                ))}
                <div className="option-row">
                  <button type="button" onClick={() => setPlans((p) => [...p, EMPTY_PLAN()])}>
                    + Plan
                  </button>
                  <button
                    type="button"
                    className="primary"
                    disabled={busy || !name.trim() || !description.trim()}
                    onClick={submitForm}
                  >
                    {busy ? "Processing…" : "Add & index"}
                  </button>
                </div>
              </div>
            )}

            {tab === "json" && (
              <div className="catalog-form">
                <textarea
                  rows={12}
                  value={jsonText}
                  onChange={(e) => setJsonText(e.target.value)}
                  className="catalog-json"
                />
                <div className="option-row">
                  <button type="button" onClick={validateJson} disabled={busy}>
                    Validate
                  </button>
                  <button type="button" className="primary" onClick={importJson} disabled={busy}>
                    Import & index
                  </button>
                </div>
                {validation && (
                  <div className={`debug-coachmark ${validation.valid ? "" : "warn"}`}>
                    {validation.valid ? (
                      <p>Valid — {validation.products.length} product(s) ready to import.</p>
                    ) : (
                      <ul>
                        {validation.errors.map((err, i) => (
                          <li key={i}>{err}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}

            {error && <div className="debug-coachmark warn">{error}</div>}
            <PipelineThoughtStream
              events={streamEvents}
              running={streaming}
              error={streamError}
              includeIngest
            />
            {lastResult && (
              <div className="debug-coachmark">
                <strong>Last ingest</strong>
                <ul>
                  {lastResult.products.map((p) => (
                    <li key={p.product_id}>
                      {p.name} — <span className={`status-${p.status}`}>{p.status}</span>
                      {p.error ? ` (${p.error})` : ""}
                    </li>
                  ))}
                </ul>
                <div className="option-row" style={{ marginTop: "0.75rem" }}>
                  {onGoToChat && (
                    <button type="button" className="primary" onClick={onGoToChat}>
                      Go to chat
                    </button>
                  )}
                  {lastResult.products[0]?.name && lastResult.products[0].status === "indexed" && (
                    <button
                      type="button"
                      onClick={() => onTryInChat(lastResult.products[0].name)}
                    >
                      Try in chat
                    </button>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </BentoTile>

      <BentoTile span="pipeline" title="Your products">
        {products.length === 0 ? (
          <div className="empty">
            {isDemo ? "No products listed for demo here." : "No products yet. Drop a file or use the form."}
          </div>
        ) : (
          <div className="review-list">
            {products.map((p) => (
              <div key={p.product_id} className="review-card">
                <h3>{p.name}</h3>
                <div className="review-card__meta">
                  {p.product_id} · <span className={`status-${p.status}`}>{p.status}</span>
                </div>
                {p.flags.length > 0 && (
                  <div className="option-row">
                    {p.flags.map((f) => (
                      <span key={f} className="badge">
                        {f}
                      </span>
                    ))}
                  </div>
                )}
                {p.status === "indexed" && (
                  <button type="button" className="primary" onClick={() => onTryInChat(p.name)}>
                    Try in chat
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </BentoTile>
    </BentoGrid>
  );
}
