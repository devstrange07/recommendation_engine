import { useEffect } from "react";
import type { PipelineRunMetrics } from "../api";

const PHASE_LABELS: Record<string, string> = {
  ingest: "Ingest",
  preprocess: "Preprocess",
  normalize: "Normalize",
  merge: "Merge",
  index: "Index",
  eval_profile: "Eval profile",
};

type Props = {
  metrics: PipelineRunMetrics;
  onClose: () => void;
};

function formatSeconds(s: number): string {
  if (s < 10) return `${s.toFixed(1)}s`;
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

function formatCost(usd: number, estimated: boolean): string {
  if (usd <= 0) return "—";
  const prefix = estimated ? "~" : "";
  if (usd < 0.01) return `${prefix}$${usd.toFixed(4)}`;
  return `${prefix}$${usd.toFixed(3)}`;
}

export function sumMetrics(items: PipelineRunMetrics[]): PipelineRunMetrics | null {
  if (items.length === 0) return null;
  if (items.length === 1) return items[0];

  const phaseMap = new Map<string, number>();
  let prompt = 0;
  let completion = 0;
  let embedding = 0;
  let totalSeconds = 0;

  for (const m of items) {
    totalSeconds += m.total_seconds;
    prompt += m.tokens?.prompt ?? 0;
    completion += m.tokens?.completion ?? 0;
    embedding += m.tokens?.embedding ?? 0;
    for (const p of m.phases ?? []) {
      phaseMap.set(p.phase, (phaseMap.get(p.phase) ?? 0) + p.seconds);
    }
  }

  const order = [
    "ingest",
    "preprocess",
    "normalize",
    "merge",
    "index",
    "eval_profile",
  ];
  const phases = [
    ...order.filter((id) => phaseMap.has(id)).map((id) => ({
      phase: id,
      seconds: Math.round((phaseMap.get(id) ?? 0) * 1000) / 1000,
    })),
    ...[...phaseMap.keys()]
      .filter((id) => !order.includes(id))
      .map((id) => ({
        phase: id,
        seconds: Math.round((phaseMap.get(id) ?? 0) * 1000) / 1000,
      })),
  ];

  const cost = items.reduce((acc, m) => acc + (m.cost_usd ?? 0), 0);

  return {
    total_seconds: Math.round(totalSeconds * 1000) / 1000,
    phases,
    tokens: {
      prompt,
      completion,
      embedding,
      total: prompt + completion + embedding,
    },
    cost_usd: Math.round(cost * 1_000_000) / 1_000_000,
    cost_estimated: true,
  };
}

export default function PipelineRunSummaryModal({ metrics, onClose }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const tokens = metrics.tokens ?? {
    prompt: 0,
    completion: 0,
    embedding: 0,
    total: 0,
  };

  return (
    <div
      className="run-summary-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Pipeline run summary"
      onClick={onClose}
    >
      <div className="run-summary-modal" onClick={(e) => e.stopPropagation()}>
        <div className="run-summary-modal__header">
          <h2>Run complete</h2>
          <button type="button" className="run-summary-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <p className="run-summary-modal__total">
          Total time <strong>{formatSeconds(metrics.total_seconds)}</strong>
        </p>

        <table className="run-summary-table">
          <thead>
            <tr>
              <th>Phase</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {(metrics.phases ?? []).map((p) => (
              <tr key={p.phase}>
                <td>{PHASE_LABELS[p.phase] ?? p.phase}</td>
                <td>{formatSeconds(p.seconds)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="run-summary-tokens">
          <div>
            <span className="label">Tokens</span>
            <span className="value">
              {tokens.total > 0
                ? `${tokens.total.toLocaleString()} total`
                : "—"}
            </span>
          </div>
          {tokens.total > 0 && (
            <p className="run-summary-token-detail">
              prompt {tokens.prompt.toLocaleString()} · completion{" "}
              {tokens.completion.toLocaleString()}
              {tokens.embedding > 0
                ? ` · embedding ${tokens.embedding.toLocaleString()}`
                : ""}
            </p>
          )}
          <div>
            <span className="label">Est. cost</span>
            <span className="value">
              {formatCost(metrics.cost_usd ?? 0, metrics.cost_estimated !== false)}
            </span>
          </div>
          {(metrics.cost_usd ?? 0) > 0 && metrics.cost_estimated !== false && (
            <p className="run-summary-cost-note">Estimated from configured rates</p>
          )}
        </div>

        <div className="run-summary-modal__actions">
          <button type="button" className="primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
