type Props = {
  mode: "turn" | "pipeline";
  activeNodes: string[];
  latency?: Record<string, number>;
  stageCounts?: Record<string, number>;
};

const TURN_NODES = [
  "received",
  "llm_decided_search",
  "llm_decided_no_search",
  "filters_extracted",
  "qdrant_query",
  "fallback_none",
  "injected",
  "llm_pitched",
];

const PIPELINE_NODES = ["raw", "staged", "normalized", "canonical", "review_queue"];

export default function FlowMindmap({ mode, activeNodes, latency, stageCounts }: Props) {
  const nodes = mode === "turn" ? TURN_NODES : PIPELINE_NODES;

  function isActive(node: string) {
    return activeNodes.some((a) => a === node || a.startsWith(node) || (node === "injected" && a.startsWith("injected_")));
  }

  function label(node: string) {
    if (mode === "pipeline" && stageCounts) {
      return `${node} (${stageCounts[node] ?? 0})`;
    }
    return node;
  }

  function msFor(node: string) {
    if (!latency) return null;
    if (node === "filters_extracted" || node === "llm_decided_search") return latency.extract;
    if (node === "qdrant_query") return latency.qdrant;
    if (node === "llm_pitched") return latency.final_llm;
    return null;
  }

  return (
    <div className={`mindmap mindmap--${mode}`}>
      {nodes.map((n) => {
        const ms = msFor(n);
        const active =
          isActive(n) ||
          (n === "fallback_none" && activeNodes.some((a) => a.startsWith("fallback_")));
        return (
          <div key={n} className={`node ${active ? "active" : ""}`}>
            {label(n)}
            {ms != null ? <span className="ms">{Math.round(ms)} ms</span> : null}
          </div>
        );
      })}
      {mode === "turn" &&
        activeNodes
          .filter((a) => a.startsWith("fallback_") && a !== "fallback_none")
          .map((a) => (
            <div key={a} className="node active">
              {a}
            </div>
          ))}
    </div>
  );
}
