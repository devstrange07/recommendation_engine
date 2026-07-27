import { useEffect, useState } from "react";
import {
  ProgressEvent,
  ReviewFlagItem,
  getPipelineStatus,
  getReviewQueue,
  postOverride,
  streamPipelineRun,
} from "../api";
import BentoGrid from "./BentoGrid";
import BentoTile from "./BentoTile";
import FlowMindmap from "./FlowMindmap";
import PipelineThoughtStream from "./PipelineThoughtStream";

const STAT_KEYS = ["raw", "staged", "canonical", "review_queue"] as const;

export default function ReviewQueue({ tenantId = "demo" }: { tenantId?: string }) {
  const [items, setItems] = useState<ReviewFlagItem[]>([]);
  const [status, setStatus] = useState<Record<string, number>>({});
  const [custom, setCustom] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [streamEvents, setStreamEvents] = useState<ProgressEvent[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);

  async function refresh() {
    setItems(await getReviewQueue(tenantId));
    const st = await getPipelineStatus(tenantId);
    setStatus(st.stage_counts || {});
  }

  useEffect(() => {
    refresh().catch(console.error);
  }, [tenantId]);

  async function answer(item: ReviewFlagItem, value: string) {
    await postOverride(
      {
        product_id: item.product_id,
        field: item.flag.field,
        value,
        flag_type: item.flag.type,
      },
      tenantId
    );
    await refresh();
  }

  async function rerun() {
    setBusy(true);
    setMsg("");
    setStreamError(null);
    setStreamEvents([]);
    try {
      const res = await streamPipelineRun(tenantId, (ev) => {
        setStreamEvents((prev) => [...prev, ev]);
      });
      setMsg(res.summary || "Pipeline complete");
      await refresh();
    } catch (e) {
      const err = String(e);
      setMsg(err);
      setStreamError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <BentoGrid layout="review">
      <div className="stat-chips">
        {STAT_KEYS.map((key) => (
          <div key={key} className={`stat-chip stat-chip--${key}`}>
            <div className="label">{key.replace("_", " ")}</div>
            <div className="value">{status[key] ?? 0}</div>
          </div>
        ))}
      </div>
      <BentoTile
        span="queue"
        title="Review Queue"
        headerRight={
          <button className="primary" onClick={rerun} disabled={busy}>
            {busy ? "Running…" : "Re-run pipeline"}
          </button>
        }
      >
        <PipelineThoughtStream
          events={streamEvents}
          running={busy}
          error={streamError}
          includeIngest={false}
        />
        {msg && !busy && <div className="debug-body">{msg}</div>}
        <div className="review-list">
          {items.length === 0 && <div className="empty">No flags in queue.</div>}
          {items.map((item, idx) => {
            const key = `${item.product_id}:${item.flag.field}:${idx}`;
            return (
              <div className="review-card" key={key}>
                <h3>
                  {item.product_name || item.product_id} — {item.flag.type}
                </h3>
                <div className="review-card__meta">
                  field: {item.flag.field}
                </div>
                <p>{item.flag.issue}</p>
                <div className="option-row">
                  {item.flag.options.map((opt) => (
                    <button
                      key={opt}
                      className={opt === item.flag.recommended ? "recommended" : ""}
                      onClick={() => answer(item, opt)}
                    >
                      {opt}
                      {opt === item.flag.recommended ? " ★" : ""}
                    </button>
                  ))}
                </div>
                <div className="option-row">
                  <input
                    placeholder="Custom value"
                    value={custom[key] || ""}
                    onChange={(e) => setCustom({ ...custom, [key]: e.target.value })}
                  />
                  <button
                    onClick={() => custom[key] && answer(item, custom[key])}
                    disabled={!custom[key]}
                  >
                    Save custom
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </BentoTile>
      <BentoTile span="pipeline" title="Pipeline flow">
        <FlowMindmap
          mode="pipeline"
          activeNodes={Object.keys(status).filter((k) => (status[k] ?? 0) > 0)}
          stageCounts={status}
        />
      </BentoTile>
    </BentoGrid>
  );
}
