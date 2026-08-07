import { useEffect, useMemo, useRef, useState } from "react";
import type { ProgressEvent, ProgressPhase } from "../api";

const PHASE_ORDER: ProgressPhase[] = [
  "ingest",
  "preprocess",
  "normalize",
  "merge",
  "index",
  "eval_profile",
  "done",
];

const PHASE_LABELS: Record<ProgressPhase, string> = {
  ingest: "Ingest",
  preprocess: "Preprocess",
  normalize: "Normalize",
  merge: "Merge",
  index: "Index",
  eval_profile: "Eval profile",
  done: "Done",
};

type PhaseState = "pending" | "active" | "done" | "error";

type PhaseProgress = {
  current: number;
  total: number;
  unit: "products" | "batches";
};

type PhaseView = {
  id: ProgressPhase;
  label: string;
  state: PhaseState;
  lines: string[];
  latestMessage: string | null;
  progress: PhaseProgress | null;
};

type Props = {
  events: ProgressEvent[];
  running: boolean;
  error?: string | null;
  /** When false, hide the ingest phase (pipeline re-run). Default true. */
  includeIngest?: boolean;
};

type PhaseAccum = {
  lines: string[];
  latestMessage: string | null;
  processed: number | null;
  totalProducts: number | null;
  batchTotal: number | null;
  completedBatches: Set<number>;
};

function emptyAccum(): PhaseAccum {
  return {
    lines: [],
    latestMessage: null,
    processed: null,
    totalProducts: null,
    batchTotal: null,
    completedBatches: new Set(),
  };
}

function progressFromAccum(acc: PhaseAccum): PhaseProgress | null {
  if (
    acc.processed != null &&
    acc.totalProducts != null &&
    acc.totalProducts > 0
  ) {
    return {
      current: Math.min(acc.processed, acc.totalProducts),
      total: acc.totalProducts,
      unit: "products",
    };
  }
  if (acc.batchTotal != null && acc.batchTotal > 0) {
    return {
      current: Math.min(acc.completedBatches.size, acc.batchTotal),
      total: acc.batchTotal,
      unit: "batches",
    };
  }
  return null;
}

function buildPhases(
  events: ProgressEvent[],
  includeIngest: boolean
): PhaseView[] {
  const ids = includeIngest
    ? PHASE_ORDER
    : PHASE_ORDER.filter((p) => p !== "ingest");

  const byPhase: Partial<Record<ProgressPhase, PhaseAccum>> = {};
  /** Index of the replaceable progress line for each (phase, batch_index). */
  const lastBatchLineIndex: Partial<Record<ProgressPhase, Record<number, number>>> = {};
  const started = new Set<ProgressPhase>();
  const finished = new Set<ProgressPhase>();
  let errored: ProgressPhase | null = null;

  for (const ev of events) {
    const acc = byPhase[ev.phase] || emptyAccum();
    const batchIndex = ev.detail?.batch_index;

    if (typeof batchIndex === "number") {
      const byBatch = lastBatchLineIndex[ev.phase] || {};
      const existing = byBatch[batchIndex];
      if (existing !== undefined) {
        acc.lines[existing] = ev.message;
      } else {
        byBatch[batchIndex] = acc.lines.length;
        lastBatchLineIndex[ev.phase] = byBatch;
        acc.lines.push(ev.message);
      }
      if (/\bcomplete\b/i.test(ev.message)) {
        acc.completedBatches.add(batchIndex);
      }
    } else {
      acc.lines.push(ev.message);
    }

    acc.latestMessage = ev.message;

    const detail = ev.detail;
    if (detail) {
      if (typeof detail.processed === "number") acc.processed = detail.processed;
      if (typeof detail.total_products === "number") {
        acc.totalProducts = detail.total_products;
      }
      if (typeof detail.batch_total === "number") {
        acc.batchTotal = detail.batch_total;
      }
    }

    byPhase[ev.phase] = acc;

    if (ev.type === "error") {
      errored = ev.phase;
    } else if (ev.type === "phase_start" || ev.type === "subtask") {
      started.add(ev.phase);
    } else if (ev.type === "phase_done") {
      started.add(ev.phase);
      finished.add(ev.phase);
    } else if (ev.type === "done") {
      started.add("done");
      finished.add("done");
    }
  }

  return ids.map((id) => {
    let state: PhaseState = "pending";
    if (errored === id) state = "error";
    else if (finished.has(id)) state = "done";
    else if (started.has(id)) state = "active";

    const acc = byPhase[id] || emptyAccum();
    return {
      id,
      label: PHASE_LABELS[id],
      state,
      lines: acc.lines,
      latestMessage: acc.latestMessage,
      progress: progressFromAccum(acc),
    };
  });
}

export default function PipelineThoughtStream({
  events,
  running,
  error,
  includeIngest = true,
}: Props) {
  const phases = useMemo(() => buildPhases(events, includeIngest), [events, includeIngest]);
  const [manualOpen, setManualOpen] = useState<Partial<Record<ProgressPhase, boolean>>>({});
  const [detailsOpen, setDetailsOpen] = useState<Partial<Record<ProgressPhase, boolean>>>({});
  const logRefs = useRef<Partial<Record<ProgressPhase, HTMLDivElement | null>>>({});

  useEffect(() => {
    for (const phase of phases) {
      if (phase.state !== "active" || !detailsOpen[phase.id]) continue;
      const el = logRefs.current[phase.id];
      if (el) el.scrollTop = el.scrollHeight;
    }
  }, [phases, events, detailsOpen]);

  if (!running && events.length === 0 && !error) {
    return null;
  }

  return (
    <div className="thought-stream" role="status" aria-live="polite">
      <div className="thought-stream__header">
        {running
          ? "Working through the pipeline…"
          : error
            ? "Stopped with an error"
            : "Complete"}
      </div>
      <div className="thought-stream__phases">
        {phases.map((phase) => {
          const defaultOpen = phase.state === "active" || phase.state === "error";
          const open =
            manualOpen[phase.id] !== undefined ? !!manualOpen[phase.id] : defaultOpen;
          const showLive =
            open &&
            (phase.state === "active" || phase.state === "error") &&
            (phase.progress != null || phase.latestMessage != null);
          const showDetailsToggle = open && phase.lines.length > 1;
          const details = !!detailsOpen[phase.id];

          return (
            <div
              key={phase.id}
              className={`thought-phase thought-phase--${phase.state}${open ? " thought-phase--open" : ""}`}
            >
              <button
                type="button"
                className="thought-phase__head"
                onClick={() =>
                  setManualOpen((prev) => ({ ...prev, [phase.id]: !open }))
                }
                disabled={phase.state === "pending" && phase.lines.length === 0}
              >
                <span className="thought-phase__marker" aria-hidden>
                  {phase.state === "done"
                    ? "✓"
                    : phase.state === "active"
                      ? "●"
                      : phase.state === "error"
                        ? "!"
                        : "○"}
                </span>
                <span className="thought-phase__label">{phase.label}</span>
                {phase.state === "active" && phase.progress && (
                  <span className="thought-phase__fraction">
                    {phase.progress.current}/{phase.progress.total}
                  </span>
                )}
                {phase.state === "active" && (
                  <span className="thought-phase__pulse">running</span>
                )}
              </button>
              {showLive && (
                <div className="thought-phase__live">
                  {phase.progress && (
                    <div className="thought-phase__progress">
                      <div
                        className="thought-phase__bar"
                        role="progressbar"
                        aria-valuenow={phase.progress.current}
                        aria-valuemin={0}
                        aria-valuemax={phase.progress.total}
                        aria-label={`${phase.label} progress`}
                      >
                        <div
                          className="thought-phase__bar-fill"
                          style={{
                            width: `${Math.min(
                              100,
                              (phase.progress.current / phase.progress.total) * 100
                            )}%`,
                          }}
                        />
                      </div>
                      <span className="thought-phase__progress-label">
                        {phase.progress.current} / {phase.progress.total}{" "}
                        {phase.progress.unit}
                      </span>
                    </div>
                  )}
                  {phase.latestMessage && (
                    <div className="thought-phase__current" title={phase.latestMessage}>
                      {phase.latestMessage}
                    </div>
                  )}
                </div>
              )}
              {showDetailsToggle && (
                <button
                  type="button"
                  className="thought-phase__details-toggle"
                  onClick={() =>
                    setDetailsOpen((prev) => ({
                      ...prev,
                      [phase.id]: !details,
                    }))
                  }
                >
                  {details ? "Hide details" : "Details"}
                </button>
              )}
              {open && details && phase.lines.length > 0 && (
                <div
                  className="thought-phase__log"
                  ref={(el) => {
                    logRefs.current[phase.id] = el;
                  }}
                >
                  {phase.lines.map((line, i) => (
                    <div key={`${phase.id}-${i}`} className="thought-phase__line">
                      {line}
                    </div>
                  ))}
                </div>
              )}
              {open &&
                phase.state === "done" &&
                !details &&
                phase.lines.length === 1 &&
                phase.latestMessage && (
                  <div className="thought-phase__live">
                    <div className="thought-phase__current" title={phase.latestMessage}>
                      {phase.latestMessage}
                    </div>
                  </div>
                )}
            </div>
          );
        })}
      </div>
      {error && <div className="thought-stream__error">{error}</div>}
    </div>
  );
}
