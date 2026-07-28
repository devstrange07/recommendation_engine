import { Fragment, useEffect, useMemo, useState } from "react";
import { DebugTrace, ProductCard, getProduct } from "../api";

type PhaseId = "received" | "understand" | "retrieve" | "fallback" | "inject" | "pitch";

type Phase = {
  id: PhaseId;
  label: string;
  ms: number | null;
  status: "ok" | "warn" | "skip";
  statusLabel: string;
};

type Hit = DebugTrace["hits"][number];

type Props = {
  debug: DebugTrace | null;
  shortlist?: ProductCard[];
  tenantId?: string;
  country?: string;
};

const COUNTRY_CURRENCY: Record<string, string> = {
  IN: "INR",
  US: "USD",
  GB: "GBP",
};

function currencyForCountry(country: string): string {
  return COUNTRY_CURRENCY[country.toUpperCase()] ?? "INR";
}

function flowHas(flow: string[], pred: (e: string) => boolean) {
  return flow.some(pred);
}

function buildPhases(debug: DebugTrace): Phase[] {
  const flow = debug.turn_flow;
  const searched = flowHas(flow, (e) => e === "qdrant_query" || e === "llm_decided_search");
  const noSearch = flowHas(flow, (e) => e === "llm_decided_no_search");
  const understood = searched || noSearch || flowHas(flow, (e) => e === "filters_extracted");
  const retrieved = flowHas(flow, (e) => e === "qdrant_query");
  const fallbackActive =
    debug.fallback.triggered || flowHas(flow, (e) => e.startsWith("fallback_"));
  const injected = flowHas(flow, (e) => e.startsWith("injected"));
  const pitched = flowHas(flow, (e) => e === "llm_pitched");

  const phases: Phase[] = [
    { id: "received", label: "Received", ms: null, status: "ok", statusLabel: "ok" },
  ];

  if (understood) {
    phases.push({
      id: "understand",
      label: "Understand",
      ms: debug.latency_ms.extract ?? null,
      status: "ok",
      statusLabel: noSearch && !searched ? "no search" : "ok",
    });
  }

  if (retrieved) {
    phases.push({
      id: "retrieve",
      label: "Retrieve",
      ms: debug.latency_ms.qdrant ?? null,
      status: "ok",
      statusLabel: `${debug.hits.length} hit${debug.hits.length === 1 ? "" : "s"}`,
    });
  }

  if (fallbackActive) {
    phases.push({
      id: "fallback",
      label: "Fallback",
      ms: null,
      status: debug.fallback.triggered ? "warn" : "ok",
      statusLabel: debug.fallback.action ?? (debug.fallback.triggered ? "triggered" : "none"),
    });
  }

  if (injected) {
    const cardEvent = flow.find((e) => e.startsWith("injected"));
    phases.push({
      id: "inject",
      label: "Inject",
      ms: null,
      status: "ok",
      statusLabel: cardEvent?.replace("injected_", "").replace("_cards", " cards") ?? "ok",
    });
  }

  if (pitched) {
    phases.push({
      id: "pitch",
      label: "Pitch",
      ms: debug.latency_ms.final_llm ?? null,
      status: "ok",
      statusLabel: "ok",
    });
  }

  return phases;
}

function defaultPhase(phases: Phase[], debug: DebugTrace): PhaseId {
  if (debug.hits.length > 0 && phases.some((p) => p.id === "retrieve")) return "retrieve";
  return phases[phases.length - 1]?.id ?? "received";
}

function KvList({ data }: { data: Record<string, unknown> | null }) {
  if (!data || Object.keys(data).length === 0) {
    return <p className="wf-muted">(none)</p>;
  }
  return (
    <dl className="wf-kv">
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="wf-kv-row">
          <dt>{k}</dt>
          <dd>{typeof v === "object" ? JSON.stringify(v) : String(v ?? "—")}</dd>
        </div>
      ))}
    </dl>
  );
}

function RawBlock({ data, label = "Raw" }: { data: unknown; label?: string }) {
  return (
    <details className="wf-raw">
      <summary>{label}</summary>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}

function ReasoningBlock({
  text,
  reasoningTokens,
}: {
  text?: string | null;
  reasoningTokens?: number;
}) {
  const label =
    reasoningTokens != null
      ? `Reasoning summary · ${reasoningTokens} tokens`
      : text
        ? "Reasoning summary"
        : "Reasoning summary · (none)";
  return (
    <details className="wf-raw wf-reasoning">
      <summary>{label}</summary>
      {text ? <pre className="wf-prompt">{text}</pre> : <p className="wf-muted">(none)</p>}
    </details>
  );
}

function formatPrice(value: unknown, currency: string): string {
  if (value == null || value === "") return "—";
  if (typeof value === "number") return `${currency} ${value.toLocaleString()}`;
  if (typeof value === "string") return value;
  if (typeof value === "object" && !Array.isArray(value)) {
    const map = value as Record<string, unknown>;
    const preferred = map[currency];
    if (typeof preferred === "number") return `${currency} ${preferred.toLocaleString()}`;
    if (typeof preferred === "string" && preferred) return preferred;
    const entry = Object.entries(map).find(
      ([, v]) => typeof v === "number" || (typeof v === "string" && v)
    );
    if (!entry) return "—";
    const [cur, amt] = entry;
    if (typeof amt === "number") return `${cur} ${amt.toLocaleString()}`;
    return String(amt);
  }
  return "—";
}

function formatHitPrice(
  payload: Record<string, unknown> | null,
  excerpt: Record<string, unknown>,
  currency: string
): string {
  const displayCard = payload?.display_card;
  if (displayCard && typeof displayCard === "object" && !Array.isArray(displayCard)) {
    const card = (displayCard as Record<string, unknown>)[currency];
    if (typeof card === "string" && card) return card;
  }
  return formatPrice(payload?.price_min ?? excerpt.price_min, currency);
}

function formatScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(4);
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(String).filter(Boolean);
}

function HitDetail({
  hit,
  payload,
  currency,
}: {
  hit: Hit;
  payload: Record<string, unknown> | null;
  currency: string;
}) {
  const excerpt = hit.payload_excerpt ?? {};
  const title = String(payload?.title ?? excerpt.title ?? hit.id);
  const category = String(payload?.category_path ?? excerpt.category_path ?? "—");
  const pitch = String(payload?.short_pitch ?? excerpt.short_pitch ?? "—");
  const priceDisplay = formatHitPrice(payload, excerpt, currency);
  const tags = asStringList(payload?.use_case_tags);
  const audience = asStringList(payload?.target_audience);
  const offerings = Array.isArray(payload?.offerings) ? payload.offerings : [];

  return (
    <div className="hit-detail">
      <div className="hit-detail__head">
        <span className="hit-detail__rank">RRF #{hit.rrf_rank}</span>
        <h4 className="hit-detail__title">{title}</h4>
        <code className="hit-detail__id">{hit.id}</code>
      </div>
      <dl className="hit-detail__fields">
        <div>
          <dt>Category</dt>
          <dd>{category}</dd>
        </div>
        <div>
          <dt>Pitch</dt>
          <dd>{pitch}</dd>
        </div>
        <div>
          <dt>Price min</dt>
          <dd>{priceDisplay}</dd>
        </div>
        {tags.length > 0 && (
          <div>
            <dt>Use cases</dt>
            <dd className="hit-detail__tags">
              {tags.map((t) => (
                <span key={t} className="ret-tag">
                  {t}
                </span>
              ))}
            </dd>
          </div>
        )}
        {audience.length > 0 && (
          <div>
            <dt>Audience</dt>
            <dd className="hit-detail__tags">
              {audience.map((t) => (
                <span key={t} className="ret-tag">
                  {t}
                </span>
              ))}
            </dd>
          </div>
        )}
        {offerings.length > 0 && (
          <div>
            <dt>Plans</dt>
            <dd>
              <ul className="hit-detail__plans">
                {offerings.map((o, i) => {
                  const off = o as Record<string, unknown>;
                  return (
                    <li key={String(off.name ?? i)}>
                      {String(off.name ?? `Plan ${i + 1}`)}
                      {off.billing_period != null && (
                        <span className="hit-detail__plan-meta"> · {String(off.billing_period)}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </dd>
          </div>
        )}
      </dl>
      {payload && <RawBlock data={payload} label="Full product JSON" />}
    </div>
  );
}

export default function DebugPanel({
  debug,
  shortlist = [],
  tenantId = "demo",
  country = "IN",
}: Props) {
  const currency = currencyForCountry(country);
  const phases = useMemo(() => (debug ? buildPhases(debug) : []), [debug]);
  const [selected, setSelected] = useState<PhaseId>("received");
  const [selectedHitId, setSelectedHitId] = useState<string | null>(null);
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [payloadLoading, setPayloadLoading] = useState(false);

  const hitById = useMemo(() => {
    const map = new Map<string, Hit>();
    debug?.hits.forEach((h) => map.set(h.id, h));
    return map;
  }, [debug]);

  const shortlistIds = useMemo(() => new Set(shortlist.map((c) => c.id)), [shortlist]);

  useEffect(() => {
    if (!debug) return;
    setSelected(defaultPhase(phases, debug));
    setSelectedHitId(null);
    setPayload(null);
  }, [debug, phases]);

  async function openHit(id: string) {
    if (selectedHitId === id) {
      setSelectedHitId(null);
      setPayload(null);
      return;
    }
    setSelectedHitId(id);
    setPayloadLoading(true);
    try {
      const product = (await getProduct(id, tenantId)) as Record<string, unknown>;
      setPayload(product);
    } catch (e) {
      setPayload({ error: String(e) });
    } finally {
      setPayloadLoading(false);
    }
  }

  if (!debug) {
    return (
      <>
        <div className="debug-coachmark">
          After your first message, this panel shows the shortlisted recommendations (what a sales
          agent would inject), ranked retrieval hits, and the turn phases behind them.
        </div>
        <div className="empty">Send a chat message to see retrieval evidence.</div>
      </>
    );
  }

  const totalMs = Object.values(debug.latency_ms).reduce((a, b) => a + (b || 0), 0);
  const totalTokens = Object.values(debug.tokens).reduce((a, b) => a + (b || 0), 0);
  const maxMs = Math.max(totalMs, 1);
  const selectedPhase = phases.find((p) => p.id === selected) ?? phases[0];

  const decision = debug.turn_flow.includes("llm_decided_no_search")
    ? "No search"
    : debug.turn_flow.includes("llm_decided_search")
      ? "Search"
      : "—";

  return (
    <div className="retrieval-panel">
      <div className="ret-summary">
        <span>
          <strong>{Math.round(totalMs)}</strong> ms
        </span>
        <span className="wf-header-sep" />
        <span>
          <strong>{totalTokens}</strong> tokens
        </span>
        <span className="wf-header-sep" />
        <span>
          <strong>{debug.hits.length}</strong> hits
        </span>
        <span className="wf-header-sep" />
        <span>
          <strong>{shortlist.length}</strong> shortlisted
        </span>
        <span className={`ret-chip${decision === "No search" ? " muted" : ""}`}>{decision}</span>
        {debug.fallback.triggered && (
          <span className="ret-chip warn">fallback: {debug.fallback.action ?? "yes"}</span>
        )}
      </div>

      <div className="retrieval-panel__scroll">
        <section className="ret-section ret-section--hero">
          <header className="ret-section__head">
            <h3>Recommended for inject</h3>
            <p>Shortlist that feeds the sales-agent prompt (up to 3).</p>
          </header>
          {shortlist.length === 0 ? (
            <p className="wf-muted">No products shortlisted this turn.</p>
          ) : (
            <div className="shortlist-grid">
              {shortlist.map((card, i) => {
                const hit = hitById.get(card.id);
                return (
                  <article key={card.id} className="shortlist-card">
                    <div className="shortlist-card__rank">{i + 1}</div>
                    <div className="shortlist-card__body">
                      <div className="shortlist-card__title-row">
                        <h4>{card.title}</h4>
                        <code>{card.id}</code>
                      </div>
                      <p className="shortlist-card__pitch">{card.pitch}</p>
                      <div className="shortlist-card__price">{card.price_display}</div>
                      {card.plan_names?.length ? (
                        <ul className="shortlist-card__plans">
                          {card.plan_names.map((name) => (
                            <li key={name}>{name}</li>
                          ))}
                        </ul>
                      ) : null}
                      <div className="shortlist-card__meta">
                        {hit ? (
                          <button
                            type="button"
                            className="ret-link"
                            onClick={() => openHit(card.id)}
                          >
                            RRF #{hit.rrf_rank}
                          </button>
                        ) : (
                          <span className="wf-muted">Not in hit list</span>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        <section className="ret-section">
          <header className="ret-section__head">
            <h3>Ranked retrieval hits</h3>
            <p>Hybrid search results before / including inject candidates.</p>
          </header>
          {debug.hits.length === 0 ? (
            <p className="wf-muted">No hits this turn.</p>
          ) : (
            <div className="hit-list">
              {debug.hits.map((h) => {
                const excerpt = h.payload_excerpt ?? {};
                const isSelected = selectedHitId === h.id;
                const isShortlisted = shortlistIds.has(h.id);
                return (
                  <Fragment key={h.id}>
                    <button
                      type="button"
                      className={`hit-row${isSelected ? " selected" : ""}${isShortlisted ? " shortlisted" : ""}`}
                      onClick={() => openHit(h.id)}
                    >
                      <span className="hit-row__rank">{h.rrf_rank}</span>
                      <span className="hit-row__main">
                        <span className="hit-row__title">{String(excerpt.title ?? h.id)}</span>
                        <span className="hit-row__cat">
                          {String(excerpt.category_path ?? "—")}
                        </span>
                        <span className="hit-row__pitch">
                          {String(excerpt.short_pitch ?? "")}
                        </span>
                      </span>
                      <span className="hit-row__side">
                        <span className="hit-row__price">{formatPrice(excerpt.price_min, currency)}</span>
                        <div className="hit-row__scores">
                          <span className="hit-row__score">Semantic: {formatScore(h.semantic_score)}</span>
                          <span className="hit-row__score">RRF: {formatScore(h.rrf_score)}</span>
                        </div>
                        {isShortlisted && <span className="ret-chip catalog">shortlisted</span>}
                        {h.review_pending && <span className="badge">review</span>}
                      </span>
                    </button>
                    {isSelected && (
                      <div className="hit-detail-wrap">
                        {payloadLoading ? (
                          <p className="wf-muted">Loading product…</p>
                        ) : (
                          <HitDetail hit={h} payload={payload} currency={currency} />
                        )}
                      </div>
                    )}
                  </Fragment>
                );
              })}
            </div>
          )}
        </section>

        <section className="ret-section ret-section--phases">
          <header className="ret-section__head">
            <h3>Turn phases</h3>
            <p>Pipeline steps for this reply.</p>
          </header>

          <div className="wf-stepper" role="listbox" aria-label="Turn phases">
            {phases.map((p) => {
              const widthPct = p.ms != null && p.ms > 0 ? Math.max(8, (p.ms / maxMs) * 100) : 6;
              const isSelected = selected === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className={`wf-step${isSelected ? " selected" : ""}${p.status === "warn" ? " warn" : ""}`}
                  onClick={() => setSelected(p.id)}
                >
                  <span className="wf-step__label">{p.label}</span>
                  <span className={`wf-chip${p.status === "warn" ? " warn" : ""}`}>
                    {p.statusLabel}
                  </span>
                  <span className="wf-ms">{p.ms != null ? `${Math.round(p.ms)} ms` : "—"}</span>
                  <div className="wf-track">
                    <div
                      className={`wf-bar${p.status === "warn" ? " warn" : ""}${p.ms == null || p.ms === 0 ? " instant" : ""}`}
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                </button>
              );
            })}
          </div>

          <div className="wf-detail wf-detail--inline">
            <h3 className="wf-detail-title">{selectedPhase?.label ?? "Phase"}</h3>

            {selected === "received" && (
              <p className="wf-muted">
                Turn received. Downstream phases show how the reply was built.
              </p>
            )}

            {selected === "understand" && (
              <div className="wf-detail-body">
                <p>
                  Decision: <strong>{decision}</strong>
                  {debug.tokens.query_understanding != null && (
                    <> · {debug.tokens.query_understanding} tokens</>
                  )}
                  {debug.tokens.reasoning_understand != null && (
                    <> · {debug.tokens.reasoning_understand} reasoning</>
                  )}
                  {debug.latency_ms.extract != null && (
                    <> · {Math.round(debug.latency_ms.extract)} ms</>
                  )}
                </p>
                <h4>Current filters</h4>
                <KvList data={debug.extracted_filters} />
                <h4>Previous filters</h4>
                <KvList data={debug.previous_filters} />
                <RawBlock
                  data={{ current: debug.extracted_filters, previous: debug.previous_filters }}
                  label="Raw filters"
                />
                <ReasoningBlock
                  text={debug.reasoning_summary_understand}
                  reasoningTokens={debug.tokens.reasoning_understand}
                />
              </div>
            )}

            {selected === "retrieve" && (
              <div className="wf-detail-body">
                {debug.qdrant_query ? (
                  <>
                    <h4>Query</h4>
                    <KvList data={debug.qdrant_query} />
                  </>
                ) : (
                  <p className="wf-muted">No query recorded.</p>
                )}
                <p className="wf-muted">
                  Hit ranking is shown above — select a row for structured product detail.
                </p>
                <RawBlock data={debug.qdrant_query} label="Raw query" />
              </div>
            )}

            {selected === "fallback" && (
              <div className="wf-detail-body">
                <p>
                  {debug.fallback.triggered ? (
                    <>
                      Triggered · action <strong>{debug.fallback.action ?? "—"}</strong>
                    </>
                  ) : (
                    <>No fallback needed</>
                  )}
                </p>
                {debug.fallback.steps.length === 0 ? (
                  <p className="wf-muted">No ladder steps.</p>
                ) : (
                  <ol className="wf-ladder">
                    {debug.fallback.steps.map((step, i) => (
                      <li key={i}>
                        <strong>{String(step.action ?? `step ${i + 1}`)}</strong>
                        {step.hits != null && <> · {String(step.hits)} hits</>}
                      </li>
                    ))}
                  </ol>
                )}
                <RawBlock data={debug.fallback} />
              </div>
            )}

            {selected === "inject" && (
              <div className="wf-detail-body">
                <pre className="wf-prompt">{debug.injected_prompt_block || "(none)"}</pre>
              </div>
            )}

            {selected === "pitch" && (
              <div className="wf-detail-body">
                <KvList
                  data={{
                    final_tokens: debug.tokens.final ?? null,
                    reasoning_final: debug.tokens.reasoning_final ?? null,
                    final_llm_ms: debug.latency_ms.final_llm ?? null,
                    all_tokens: debug.tokens,
                    all_latency_ms: debug.latency_ms,
                  }}
                />
                <RawBlock data={{ tokens: debug.tokens, latency_ms: debug.latency_ms }} />
                <ReasoningBlock
                  text={debug.reasoning_summary_final}
                  reasoningTokens={debug.tokens.reasoning_final}
                />
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
