import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CatalogProfile,
  EvalRunDetail,
  EvalRunSummary,
  EvalScenario,
  confirmEvalScenario,
  deleteEvalScenario,
  draftEvalScenario,
  generateEvalScenarios,
  getEvalProfile,
  getEvalRun,
  listEvalRuns,
  listEvalScenarios,
  regenerateEvalProfile,
  startEvalRun,
  streamEvalRun,
} from "../api";

type Props = {
  tenantId: string;
  country: string;
};

type PhaseId = "profile" | "scenarios" | "runs" | "results";
type WizardStep = "idle" | "describe" | "clarify";

type LiveHit = {
  id?: string;
  title?: string | null;
  category_path?: string | null;
  rrf_rank?: number | null;
};

type LiveTurnCard = {
  key: string;
  scenarioId: string;
  scenarioTitle?: string;
  turn: number;
  status: "pending" | "complete" | "judged";
  userMessage?: string;
  assistantReply?: string;
  searched?: boolean;
  filters?: Record<string, unknown> | null;
  hits?: LiveHit[];
  fallbackTriggered?: boolean;
  fallbackAction?: string | null;
  rubricPass?: boolean;
  rubricReasoning?: string;
  dimensionSummary?: Array<{ dimension?: string; pass?: boolean }>;
};

const PHASES: Array<{ id: PhaseId; label: string }> = [
  { id: "profile", label: "Catalog profile" },
  { id: "scenarios", label: "Scenarios" },
  { id: "runs", label: "Runs" },
  { id: "results", label: "Results" },
];

function filterChips(filters: Record<string, unknown> | null | undefined): string[] {
  if (!filters) return [];
  const chips: string[] = [];
  if (filters.semantic_query) chips.push(`q: ${String(filters.semantic_query)}`);
  if (filters.category_path) chips.push(`cat: ${String(filters.category_path)}`);
  if (filters.price_max != null) chips.push(`≤ ${String(filters.price_max)}`);
  if (filters.brand) chips.push(`brand: ${String(filters.brand)}`);
  const excludes = filters.exclude_terms;
  if (Array.isArray(excludes) && excludes.length) {
    chips.push(`exclude: ${excludes.join(", ")}`);
  }
  const attrs = filters.attribute_filters;
  if (Array.isArray(attrs) && attrs.length) {
    for (const a of attrs.slice(0, 4)) {
      if (a && typeof a === "object" && "key" in a) {
        const row = a as { key: string; op?: string; value?: unknown };
        chips.push(`${row.key}${row.op ? ` ${row.op}` : ""} ${row.value ?? ""}`.trim());
      }
    }
  }
  return chips;
}

export default function Evals({ tenantId, country }: Props) {
  const [phase, setPhase] = useState<PhaseId>("profile");
  const [profile, setProfile] = useState<CatalogProfile | null>(null);
  const [scenarios, setScenarios] = useState<EvalScenario[]>([]);
  const [runs, setRuns] = useState<EvalRunSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<EvalRunDetail | null>(null);
  const [progressMsg, setProgressMsg] = useState<string>("");
  const [liveCards, setLiveCards] = useState<LiveTurnCard[]>([]);
  const [expandedReplies, setExpandedReplies] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const liveFeedRef = useRef<HTMLDivElement | null>(null);

  const [wizard, setWizard] = useState<WizardStep>("idle");
  const [desc, setDesc] = useState("");
  const [draftId, setDraftId] = useState<string | null>(null);
  const [questions, setQuestions] = useState<Array<{ id: string; question: string }>>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [p, s, r] = await Promise.all([
        getEvalProfile(tenantId),
        listEvalScenarios(tenantId),
        listEvalRuns(tenantId),
      ]);
      setProfile(p.profile);
      setScenarios(s.scenarios);
      setRuns(r.runs);
      setSelected((prev) => {
        const ids = new Set(s.scenarios.map((x) => x.id));
        if (prev.size === 0) return ids;
        const next = new Set([...prev].filter((id) => ids.has(id)));
        return next.size ? next : ids;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [tenantId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const canEnter = useMemo(
    () =>
      ({
        profile: true,
        scenarios: !!profile,
        runs: scenarios.length > 0,
        results: runs.length > 0 || !!activeRun,
      }) satisfies Record<PhaseId, boolean>,
    [profile, scenarios.length, runs.length, activeRun]
  );

  function goTo(next: PhaseId) {
    const order = PHASES.map((p) => p.id);
    const curIdx = order.indexOf(phase);
    const nextIdx = order.indexOf(next);
    if (nextIdx <= curIdx || canEnter[next]) {
      setPhase(next);
      setError(null);
    }
  }

  function phaseIndex(id: PhaseId) {
    return PHASES.findIndex((p) => p.id === id);
  }

  function continueNext() {
    const idx = phaseIndex(phase);
    if (idx < 0 || idx >= PHASES.length - 1) return;
    const next = PHASES[idx + 1].id;
    if (!canEnter[next]) return;
    setPhase(next);
  }

  function goBack() {
    const idx = phaseIndex(phase);
    if (idx <= 0) return;
    setPhase(PHASES[idx - 1].id);
  }

  async function onRegenerateProfile() {
    setBusy(true);
    setError(null);
    try {
      const res = await regenerateEvalProfile(tenantId);
      setProfile(res.profile);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onGenerateScenarios(replace: boolean) {
    setBusy(true);
    setError(null);
    try {
      const res = await generateEvalScenarios(tenantId, 5, replace);
      setScenarios(res.scenarios);
      setSelected(new Set(res.scenarios.map((s) => s.id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteScenario(id: string) {
    if (!window.confirm(`Delete scenario ${id}?`)) return;
    setBusy(true);
    try {
      await deleteEvalScenario(tenantId, id);
      if (expandedId === id) setExpandedId(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDraft() {
    setBusy(true);
    setError(null);
    try {
      const res = await draftEvalScenario(tenantId, desc);
      setDraftId(res.draft_id);
      setQuestions(res.questions);
      setAnswers(Object.fromEntries(res.questions.map((q) => [q.id, ""])));
      setWizard("clarify");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onConfirmDraft() {
    if (!draftId) return;
    setBusy(true);
    setError(null);
    try {
      await confirmEvalScenario(tenantId, draftId, answers);
      setWizard("idle");
      setDesc("");
      setDraftId(null);
      setQuestions([]);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const el = liveFeedRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [liveCards]);

  function upsertLiveCard(card: LiveTurnCard) {
    setLiveCards((prev) => {
      const idx = prev.findIndex((c) => c.key === card.key);
      if (idx < 0) return [...prev, card];
      const next = [...prev];
      next[idx] = { ...next[idx], ...card };
      return next;
    });
  }

  function handleStreamEvent(p: Record<string, unknown>) {
    const event = String(p.event || "");
    const scenarioId = p.scenario_id != null ? String(p.scenario_id) : "";
    const turn = typeof p.turn === "number" ? p.turn : Number(p.turn) || 0;
    const title = p.scenario_title != null ? String(p.scenario_title) : undefined;
    const idx = p.scenario_index != null ? String(p.scenario_index) : "";
    const total = p.scenario_total != null ? String(p.scenario_total) : "";

    if (scenarioId && turn) {
      setProgressMsg(
        `${title || scenarioId}${idx && total ? ` (${idx}/${total})` : ""} · turn ${turn}` +
          (event ? ` · ${event}` : "")
      );
    } else {
      setProgressMsg(String(p.message || p.status || event || ""));
    }

    if (event === "turn_start" && scenarioId && turn) {
      upsertLiveCard({
        key: `${scenarioId}:${turn}`,
        scenarioId,
        scenarioTitle: title,
        turn,
        status: "pending",
      });
      return;
    }

    if ((event === "turn_complete" || event === "turn_judged") && scenarioId && turn) {
      const payload = (p.turn_payload || {}) as Record<string, unknown>;
      const fallback = (payload.fallback || {}) as Record<string, unknown>;
      const hitsRaw = Array.isArray(payload.hits) ? payload.hits : [];
      const dims = Array.isArray(payload.dimension_summary)
        ? (payload.dimension_summary as Array<{ dimension?: string; pass?: boolean }>)
        : undefined;
      upsertLiveCard({
        key: `${scenarioId}:${turn}`,
        scenarioId,
        scenarioTitle: title,
        turn,
        status: event === "turn_judged" ? "judged" : "complete",
        userMessage: payload.user_message != null ? String(payload.user_message) : undefined,
        assistantReply:
          payload.assistant_reply != null ? String(payload.assistant_reply) : undefined,
        searched: Boolean(payload.searched),
        filters: (payload.extracted_filters as Record<string, unknown>) || null,
        hits: hitsRaw as LiveHit[],
        fallbackTriggered: Boolean(fallback.triggered),
        fallbackAction: fallback.action != null ? String(fallback.action) : null,
        rubricPass: payload.rubric_pass != null ? Boolean(payload.rubric_pass) : undefined,
        rubricReasoning:
          payload.rubric_reasoning != null ? String(payload.rubric_reasoning) : undefined,
        dimensionSummary: dims,
      });
      return;
    }

    if (event === "scenario_rescored" && scenarioId) {
      const payload = (p.turn_payload || {}) as Record<string, unknown>;
      const reason =
        payload.rubric_reasoning != null
          ? String(payload.rubric_reasoning)
          : "must_use_search but no search_products";
      setLiveCards((prev) =>
        prev.map((c) =>
          c.scenarioId === scenarioId
            ? {
                ...c,
                status: "judged" as const,
                rubricPass: false,
                rubricReasoning: reason,
              }
            : c
        )
      );
      setProgressMsg(String(p.message || `Rescored ${scenarioId}`));
      return;
    }

    if (p.warning) {
      setError(String(p.warning));
    }
  }

  async function onRun() {
    setBusy(true);
    setError(null);
    setProgressMsg("Starting…");
    setLiveCards([]);
    setExpandedReplies(new Set());
    try {
      const ids = [...selected];
      const { run_id } = await startEvalRun(tenantId, {
        scenario_ids: ids.length ? ids : null,
        country,
        max_turns: 6,
      });
      await streamEvalRun(tenantId, run_id, handleStreamEvent);
      const detail = await getEvalRun(tenantId, run_id);
      setActiveRun(detail);
      await refresh();
      setPhase("results");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function openRun(runId: string) {
    setBusy(true);
    setError(null);
    try {
      setActiveRun(await getEvalRun(tenantId, runId));
      setPhase("results");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const idx = phaseIndex(phase);
  const canContinue =
    phase === "profile"
      ? !!profile
      : phase === "scenarios"
        ? scenarios.length > 0
        : phase === "runs"
          ? runs.length > 0 || !!activeRun
          : false;

  return (
    <div className="evals-page">
      <div className="evals-header">
        <h2>Retrieval evals</h2>
        <p className="muted">
          Multi-turn suite that judges <code>search_products</code> retrieval (filters + hits), not
          chat prose.
        </p>
      </div>

      <nav className="evals-stepper" aria-label="Evals phases">
        {PHASES.map((p, i) => {
          const unlocked = i <= idx || canEnter[p.id];
          const active = p.id === phase;
          const done = i < idx;
          return (
            <button
              key={p.id}
              type="button"
              className={[
                "evals-step",
                active ? "evals-step--active" : "",
                done ? "evals-step--done" : "",
                !unlocked ? "evals-step--locked" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              disabled={!unlocked}
              onClick={() => goTo(p.id)}
            >
              <span className="evals-step__num">{i + 1}</span>
              <span className="evals-step__label">{p.label}</span>
            </button>
          );
        })}
      </nav>

      {error && <div className="evals-error">{error}</div>}

      <div className="evals-phase-body">
        {phase === "profile" && (
          <section className="evals-section evals-section--plain">
            <div className="evals-section-head">
              <h3>Catalog profile</h3>
              <button type="button" className="ghost" disabled={busy} onClick={onRegenerateProfile}>
                Regenerate
              </button>
            </div>
            {!profile ? (
              <p className="muted">
                No profile yet — ingest or re-run the pipeline, then regenerate here.
              </p>
            ) : (
              <div className="evals-profile">
                <p>
                  <strong>{profile.product_count ?? "?"} products</strong>
                  {profile.generated_at ? ` · ${profile.generated_at}` : ""}
                </p>
                <p>{profile.overview}</p>
                {profile.soft_expectations && (
                  <ul className="evals-list">
                    <li>
                      In scope:{" "}
                      {(profile.soft_expectations.in_scope_domains || []).join(", ") || "—"}
                    </li>
                    <li>
                      Out of scope:{" "}
                      {(profile.soft_expectations.out_of_scope_domains || []).join(", ") || "—"}
                    </li>
                    <li>
                      Facets:{" "}
                      {(profile.soft_expectations.notable_facets || []).join(", ") || "—"}
                    </li>
                    <li>
                      Typical constraints:{" "}
                      {(profile.soft_expectations.typical_constraints || []).join(", ") || "—"}
                    </li>
                  </ul>
                )}
              </div>
            )}
          </section>
        )}

        {phase === "scenarios" && (
          <section className="evals-section evals-section--plain">
            <div className="evals-section-head">
              <h3>Scenarios</h3>
              <div className="evals-actions">
                <button type="button" disabled={busy} onClick={() => onGenerateScenarios(false)}>
                  Add more
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={busy}
                  onClick={() => onGenerateScenarios(true)}
                >
                  Replace auto
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={busy}
                  onClick={() => setWizard("describe")}
                >
                  Add scenario
                </button>
              </div>
            </div>

            {wizard !== "idle" && (
              <div className="evals-wizard">
                {wizard === "describe" && (
                  <>
                    <label>
                      Describe the scenario
                      <textarea
                        value={desc}
                        onChange={(e) => setDesc(e.target.value)}
                        rows={4}
                        placeholder="e.g. Budget family trip to Goa, 3 nights, under 40k"
                      />
                    </label>
                    <div className="evals-actions">
                      <button type="button" disabled={busy || !desc.trim()} onClick={onDraft}>
                        Ask clarifying questions
                      </button>
                      <button type="button" className="ghost" onClick={() => setWizard("idle")}>
                        Cancel
                      </button>
                    </div>
                  </>
                )}
                {wizard === "clarify" && (
                  <>
                    <p className="muted">Answer clarifying questions, then we generate test cases.</p>
                    {questions.map((q) => (
                      <label key={q.id}>
                        {q.question}
                        <input
                          value={answers[q.id] || ""}
                          onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
                        />
                      </label>
                    ))}
                    <div className="evals-actions">
                      <button type="button" disabled={busy} onClick={onConfirmDraft}>
                        Save scenario
                      </button>
                      <button type="button" className="ghost" onClick={() => setWizard("idle")}>
                        Cancel
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {scenarios.length === 0 ? (
              <p className="muted">No scenarios yet — generate from the profile or add one.</p>
            ) : (
              <ul className="evals-scenarios">
                {scenarios.map((s) => {
                  const open = expandedId === s.id;
                  return (
                    <li key={s.id} className={open ? "evals-scenario--open" : ""}>
                      <div className="evals-scenario-row">
                        <input
                          type="checkbox"
                          checked={selected.has(s.id)}
                          onChange={() => toggle(s.id)}
                          aria-label={`Select ${s.title}`}
                        />
                        <button
                          type="button"
                          className="evals-scenario-toggle"
                          onClick={() => setExpandedId(open ? null : s.id)}
                        >
                          <strong>{s.title}</strong>{" "}
                          <span className="muted">
                            ({s.source}) · {s.id}
                          </span>
                          <div className="muted">{s.description}</div>
                        </button>
                        <button
                          type="button"
                          className="ghost"
                          onClick={() => onDeleteScenario(s.id)}
                        >
                          Delete
                        </button>
                      </div>
                      {open && (
                        <div className="evals-scenario-detail">
                          <p className="muted">
                            <strong>Goal:</strong> {s.goal || "—"}
                          </p>
                          <p className="muted">
                            Soft expectations: category hints{" "}
                            {(s.soft_expectations.expected_category_hints || []).join(", ") || "—"}
                            ; must not{" "}
                            {(s.soft_expectations.must_not_domains || []).join(", ") || "—"}
                          </p>
                          {s.soft_expectations.relevance_notes && (
                            <p className="muted">{s.soft_expectations.relevance_notes}</p>
                          )}
                          <h4>Test cases</h4>
                          {(s.test_cases || []).length === 0 ? (
                            <p className="muted">No test cases on this scenario.</p>
                          ) : (
                            <ul className="evals-test-cases">
                              {s.test_cases.map((tc) => (
                                <li key={tc.id}>
                                  <strong>{tc.id}</strong>: {tc.intent}
                                  {(tc.constraints || []).length > 0 && (
                                    <ul>
                                      {tc.constraints.map((c) => (
                                        <li key={c}>{c}</li>
                                      ))}
                                    </ul>
                                  )}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        )}

        {phase === "runs" && (
          <section className="evals-section evals-section--plain">
            <div className="evals-section-head">
              <h3>Run suite</h3>
              <button type="button" disabled={busy || selected.size === 0} onClick={onRun}>
                Run selected ({selected.size}) · {country}
              </button>
            </div>
            <p className="muted">
              Selected for this run: {selected.size} of {scenarios.length} scenarios.
            </p>

            <div className="evals-live">
              <div className="evals-live__status">
                {busy || liveCards.length > 0 ? (
                  <>
                    <span className="evals-live__pulse" aria-hidden />
                    <span>{progressMsg || "Running…"}</span>
                  </>
                ) : (
                  <span className="muted">Idle — start a run to see live query / retrieval analysis.</span>
                )}
              </div>
              <div className="evals-live__feed" ref={liveFeedRef}>
                {liveCards.length === 0 ? (
                  <p className="muted evals-live__empty">
                    Live turn feed will appear here (generated query, reply, filters, hits, rubric).
                  </p>
                ) : (
                  liveCards.map((card) => {
                    const chips = filterChips(card.filters);
                    const reply = card.assistantReply || "";
                    const replyLong = reply.length > 280;
                    const replyOpen = expandedReplies.has(card.key);
                    return (
                      <article key={card.key} className="evals-live-card">
                        <header className="evals-live-card__head">
                          <span className="evals-live-card__badge">
                            {card.scenarioTitle || card.scenarioId} · turn {card.turn}
                          </span>
                          <span
                            className={
                              card.status === "judged"
                                ? card.rubricPass
                                  ? "evals-live-card__tag evals-live-card__tag--pass"
                                  : "evals-live-card__tag evals-live-card__tag--fail"
                                : "evals-live-card__tag"
                            }
                          >
                            {card.status === "pending"
                              ? "awaiting reply"
                              : card.status === "complete"
                                ? "retrieved"
                                : card.rubricPass
                                  ? "rubric pass"
                                  : "rubric fail"}
                          </span>
                        </header>

                        {card.userMessage && (
                          <div className="evals-live-card__block">
                            <div className="evals-live-card__label">Query</div>
                            <p>{card.userMessage}</p>
                          </div>
                        )}

                        {card.assistantReply != null && card.assistantReply !== "" && (
                          <div className="evals-live-card__block">
                            <div className="evals-live-card__label">Response</div>
                            <p className={replyOpen ? "" : "evals-live-card__reply--clamp"}>
                              {reply}
                            </p>
                            {replyLong && (
                              <button
                                type="button"
                                className="linkish"
                                onClick={() =>
                                  setExpandedReplies((prev) => {
                                    const next = new Set(prev);
                                    if (next.has(card.key)) next.delete(card.key);
                                    else next.add(card.key);
                                    return next;
                                  })
                                }
                              >
                                {replyOpen ? "Collapse" : "Expand reply"}
                              </button>
                            )}
                          </div>
                        )}

                        {card.status !== "pending" && (
                          <div className="evals-live-card__block evals-live-card__retrieval">
                            <div className="evals-live-card__label">
                              Retrieval ·{" "}
                              {card.searched ? "search_products called" : "no search"}
                              {card.fallbackTriggered
                                ? ` · fallback${card.fallbackAction ? `: ${card.fallbackAction}` : ""}`
                                : ""}
                            </div>
                            {chips.length > 0 && (
                              <ul className="evals-live-chips">
                                {chips.map((c) => (
                                  <li key={c}>{c}</li>
                                ))}
                              </ul>
                            )}
                            {(card.hits || []).length > 0 ? (
                              <ol className="evals-live-hits">
                                {card.hits!.map((h) => (
                                  <li key={`${h.id}-${h.rrf_rank}`}>
                                    <code>{h.id}</code>
                                    {h.title ? ` — ${h.title}` : ""}
                                    {h.category_path ? (
                                      <span className="muted"> · {h.category_path}</span>
                                    ) : null}
                                  </li>
                                ))}
                              </ol>
                            ) : card.searched ? (
                              <p className="muted">No hits returned.</p>
                            ) : null}
                          </div>
                        )}

                        {card.status === "judged" && (
                          <div className="evals-live-card__block">
                            <div className="evals-live-card__label">Rubric</div>
                            <p className="muted">{card.rubricReasoning || "—"}</p>
                            {card.dimensionSummary && card.dimensionSummary.length > 0 && (
                              <ul className="evals-live-dims">
                                {card.dimensionSummary.map((d) => (
                                  <li key={d.dimension || "?"}>
                                    {d.dimension}: {d.pass ? "pass" : "fail"}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        )}
                      </article>
                    );
                  })
                )}
              </div>
            </div>

            <h4 className="evals-subhead">Past runs</h4>
            {runs.length === 0 ? (
              <p className="muted">No runs yet — start one above.</p>
            ) : (
              <ul className="evals-runs">
                {runs.map((r) => (
                  <li key={r.run_id}>
                    <button type="button" className="linkish" onClick={() => openRun(r.run_id)}>
                      {r.run_id}
                    </button>
                    <span className="muted">
                      {" "}
                      · {r.conclusion?.overall || r.status || "—"}
                      {r.conclusion?.scenario_pass_rate != null
                        ? ` · pass rate ${r.conclusion.scenario_pass_rate}`
                        : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {phase === "results" && (
          <section className="evals-section evals-section--plain evals-results">
            {!activeRun ? (
              <p className="muted">Run a suite or open a past run from the Runs step.</p>
            ) : (
              <>
                <div className="evals-section-head">
                  <h3>Results · {activeRun.run_id}</h3>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => {
                      setActiveRun(null);
                      setPhase("runs");
                    }}
                  >
                    Back to runs
                  </button>
                </div>
                {activeRun.conclusion_md ? (
                  <pre className="evals-md">{activeRun.conclusion_md}</pre>
                ) : (
                  <p className="muted">No conclusion yet (status: {activeRun.status}).</p>
                )}
                {(() => {
                  const jsc = activeRun.conclusion?.judge_source_counts || {};
                  const stubN = Number(jsc.stub || 0);
                  const totalJudged = Object.values(jsc).reduce(
                    (a, b) => a + Number(b || 0),
                    0
                  );
                  if (stubN <= 0) return null;
                  return (
                    <div className="evals-banner evals-banner--warn" role="status">
                      {stubN} of {totalJudged} turns judged by fallback heuristic (stub), not the
                      LLM judge. Treat scores as approximate.
                    </div>
                  );
                })()}
                {activeRun.conclusion?.promptfoo_summary && (
                  <div className="evals-banner evals-banner--info" role="status">
                    Promptfoo (supplementary, not blended into overall):{" "}
                    {activeRun.conclusion.promptfoo_summary.passes ?? "—"}/
                    {activeRun.conclusion.promptfoo_summary.total ?? "—"} passed
                    {activeRun.conclusion.promptfoo_summary.pass_rate != null
                      ? ` · rate ${activeRun.conclusion.promptfoo_summary.pass_rate}`
                      : ""}
                    {activeRun.conclusion.promptfoo_summary.note
                      ? ` — ${activeRun.conclusion.promptfoo_summary.note}`
                      : ""}
                  </div>
                )}
                {(activeRun.conclusion?.per_scenario || []).some(
                  (p) => String(p.verdict) === "skipped"
                ) && (
                  <div className="evals-banner evals-banner--info" role="status">
                    Some scenarios were skipped (0 turns) and excluded from the pass-rate
                    denominator.
                  </div>
                )}
                {(activeRun.conclusion?.per_scenario || []).length > 0 && (
                  <ul className="evals-verdict-list">
                    {(activeRun.conclusion?.per_scenario || []).map((p) => (
                      <li key={String(p.scenario_id)}>
                        <span
                          className={`evals-verdict evals-verdict--${String(p.verdict || "fail")}`}
                        >
                          {String(p.verdict)}
                        </span>{" "}
                        <code>{String(p.scenario_id)}</code>
                        {p.turn_pass_rate != null ? ` · rate ${String(p.turn_pass_rate)}` : ""}
                        {` · ${String(p.turns ?? 0)} turns`}
                      </li>
                    ))}
                  </ul>
                )}
                {activeRun.scenarios &&
                  Object.entries(activeRun.scenarios).map(([sid, turns]) => (
                    <details key={sid} className="evals-turn-block">
                      <summary>
                        {sid} · {turns.length} turns
                        {turns.length === 0 ? " · skipped" : ""}
                      </summary>
                      {turns.length === 0 ? (
                        <p className="muted">No turns recorded for this scenario.</p>
                      ) : (
                        turns.map((t) => {
                          const rubric = (t.rubric || {}) as Record<string, unknown>;
                          const scores = (rubric.scores || []) as Array<Record<string, unknown>>;
                          return (
                            <div key={String(t.turn)} className="evals-turn">
                              <div>
                                <strong>Turn {String(t.turn)}</strong>: {String(t.user_message)}
                              </div>
                              <div className="muted">
                                Rubric: {rubric.pass ? "pass" : "fail"}
                                {rubric.judge_source
                                  ? ` [${String(rubric.judge_source)}]`
                                  : ""}{" "}
                                — {String(rubric.reasoning || "")}
                              </div>
                              <ul>
                                {scores.map((s) => (
                                  <li key={String(s.dimension)}>
                                    {String(s.dimension)}: {s.pass ? "pass" : "fail"} —{" "}
                                    {String(s.reasoning || "")}
                                  </li>
                                ))}
                              </ul>
                              {t.extracted_filters != null && (
                                <pre className="evals-json">
                                  {JSON.stringify(t.extracted_filters, null, 2)}
                                </pre>
                              )}
                            </div>
                          );
                        })
                      )}
                    </details>
                  ))}
              </>
            )}
          </section>
        )}
      </div>

      <footer className="evals-phase-footer">
        <button type="button" className="ghost" disabled={idx === 0 || busy} onClick={goBack}>
          Back
        </button>
        {phase !== "results" && (
          <button
            type="button"
            disabled={busy || !canContinue}
            onClick={continueNext}
            title={
              !canContinue
                ? phase === "profile"
                  ? "Generate a catalog profile first"
                  : phase === "scenarios"
                    ? "Add or generate at least one scenario"
                    : "Complete or open a run first"
                : undefined
            }
          >
            Continue
          </button>
        )}
      </footer>
    </div>
  );
}
