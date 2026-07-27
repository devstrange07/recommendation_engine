import { useEffect, useMemo, useRef, useState } from "react";
import type { ProgressEvent, ProgressPhase } from "../api";

const PHASE_ORDER: ProgressPhase[] = [
  "ingest",
  "preprocess",
  "normalize",
  "merge",
  "index",
  "done",
];

const PHASE_LABELS: Record<ProgressPhase, string> = {
  ingest: "Ingest",
  preprocess: "Preprocess",
  normalize: "Normalize",
  merge: "Merge",
  index: "Index",
  done: "Done",
};

type PhaseState = "pending" | "active" | "done" | "error";

type PhaseView = {
  id: ProgressPhase;
  label: string;
  state: PhaseState;
  lines: string[];
};

type Props = {
  events: ProgressEvent[];
  running: boolean;
  error?: string | null;
  /** When false, hide the ingest phase (pipeline re-run). Default true. */
  includeIngest?: boolean;
};

function buildPhases(
  events: ProgressEvent[],
  includeIngest: boolean
): PhaseView[] {
  const ids = includeIngest
    ? PHASE_ORDER
    : PHASE_ORDER.filter((p) => p !== "ingest");

  const linesByPhase: Partial<Record<ProgressPhase, string[]>> = {};
  const started = new Set<ProgressPhase>();
  const finished = new Set<ProgressPhase>();
  let errored: ProgressPhase | null = null;

  for (const ev of events) {
    const bucket = linesByPhase[ev.phase] || [];
    bucket.push(ev.message);
    linesByPhase[ev.phase] = bucket;

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

    return {
      id,
      label: PHASE_LABELS[id],
      state,
      lines: linesByPhase[id] || [],
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
  const logRefs = useRef<Partial<Record<ProgressPhase, HTMLDivElement | null>>>({});

  useEffect(() => {
    for (const phase of phases) {
      if (phase.state !== "active") continue;
      const el = logRefs.current[phase.id];
      if (el) el.scrollTop = el.scrollHeight;
    }
  }, [phases, events]);

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
                {phase.state === "active" && (
                  <span className="thought-phase__pulse">running</span>
                )}
              </button>
              {open && phase.lines.length > 0 && (
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
            </div>
          );
        })}
      </div>
      {error && <div className="thought-stream__error">{error}</div>}
    </div>
  );
}
