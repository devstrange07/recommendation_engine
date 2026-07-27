import { useEffect, useState } from "react";
import { getHealth, getPipelineStatus } from "../api";

const STORAGE_KEY = "prism-onboarding-v1";

export function isOnboardingDone(): boolean {
  return localStorage.getItem(STORAGE_KEY) === "done";
}

export function markOnboardingDone(): void {
  localStorage.setItem(STORAGE_KEY, "done");
}

export function clearOnboarding(): void {
  localStorage.removeItem(STORAGE_KEY);
}

type Props = {
  onComplete: () => void;
};

type Check = {
  id: string;
  label: string;
  status: "ok" | "warn" | "info" | "loading";
  hint?: string;
};

const STEPS = ["welcome", "setup", "catalog", "pipeline", "chat", "debug"] as const;

export default function Onboarding({ onComplete }: Props) {
  const [step, setStep] = useState(0);
  const [checks, setChecks] = useState<Check[]>([
    { id: "qdrant", label: "Qdrant reachable", status: "loading" },
    { id: "openai", label: "OpenAI API key", status: "loading" },
    { id: "langsmith", label: "LangSmith tracing", status: "loading" },
    { id: "catalog", label: "Catalog indexed", status: "loading" },
  ]);

  useEffect(() => {
    if (STEPS[step] !== "setup") return;
    let cancelled = false;
    (async () => {
      try {
        const [health, status] = await Promise.all([
          getHealth().catch(() => null),
          getPipelineStatus().catch(() => null),
        ]);
        if (cancelled) return;
        const canonical = status?.stage_counts?.canonical ?? 0;
        setChecks([
          {
            id: "qdrant",
            label: "Qdrant reachable",
            status: health?.qdrant_reachable ? "ok" : "warn",
            hint: health?.qdrant_reachable
              ? undefined
              : "Run `docker compose up -d` and check QDRANT_URL.",
          },
          {
            id: "openai",
            label: "OpenAI API key",
            status: health?.openai_key_present ? "ok" : "warn",
            hint: health?.openai_key_present
              ? undefined
              : "Missing key → heuristic mode. Set OPENAI_API_KEY in .env.",
          },
          {
            id: "langsmith",
            label: "LangSmith tracing",
            status: health?.langsmith_key_present ? "ok" : "info",
            hint: health?.langsmith_key_present
              ? `Project: ${health.langsmith_project || "prism"}`
              : "Optional. Set LANGSMITH_API_KEY to log AI traces.",
          },
          {
            id: "catalog",
            label: "Catalog indexed",
            status: canonical > 0 ? "ok" : "warn",
            hint:
              canonical > 0
                ? `${canonical} canonical products ready`
                : "Run `uv run python -m app.pipeline.generate_synthetic` then `run_pipeline`.",
          },
        ]);
      } catch {
        if (!cancelled) {
          setChecks((prev) =>
            prev.map((c) => ({
              ...c,
              status: "warn" as const,
              hint: "Could not reach backend — is it on port 8009?",
            }))
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [step]);

  function finish() {
    markOnboardingDone();
    onComplete();
  }

  function next() {
    if (step >= STEPS.length - 1) finish();
    else setStep((s) => s + 1);
  }

  function back() {
    setStep((s) => Math.max(0, s - 1));
  }

  const id = STEPS[step];

  return (
    <div className="onboarding-overlay" role="dialog" aria-modal="true" aria-label="Onboarding">
      <div className="onboarding-hero">
        <div className="onboarding-progress" aria-hidden>
          {STEPS.map((_, i) => (
            <span key={i} className={i === step ? "active" : i < step ? "done" : ""} />
          ))}
        </div>

        {id === "welcome" && (
          <>
            <p className="onboarding-brand">Prism</p>
            <p className="onboarding-tagline">Talk to your HybridShelf</p>
            <p>
              Turn a messy catalog into searchable products — then gather requirements, retrieve
              matches, and pitch with real prices only.
            </p>
            <div className="onboarding-actions">
              <button className="ghost" onClick={finish}>
                Skip
              </button>
              <span className="spacer" />
              <button className="primary" onClick={next}>
                Get started
              </button>
            </div>
          </>
        )}

        {id === "setup" && (
          <>
            <h2>Setup checklist</h2>
            <p>Quick health check before you explore. You can continue even if something is yellow.</p>
            <ul className="setup-list">
              {checks.map((c) => (
                <li key={c.id}>
                  <span className={`status ${c.status}`}>
                    {c.status === "loading" ? "…" : c.status === "ok" ? "OK" : c.status === "warn" ? "Check" : "Info"}
                  </span>
                  <div>
                    <div className="label">{c.label}</div>
                    {c.hint ? <p className="hint">{c.hint}</p> : null}
                  </div>
                </li>
              ))}
            </ul>
            <div className="onboarding-actions">
              <button className="ghost" onClick={back}>
                Back
              </button>
              <button className="ghost" onClick={finish}>
                Skip
              </button>
              <span className="spacer" />
              <button className="primary" onClick={next}>
                Next
              </button>
            </div>
          </>
        )}

        {id === "catalog" && (
          <>
            <h2>Demo vs your catalogs</h2>
            <p>
              The top bar lists the <strong>demo catalog</strong> (synthetic sample data) plus any
              catalogs you create. Click <strong>New catalog</strong>, name it, then upload or paste
              JSON on the Catalog page. Chat and search only see products from the selected catalog.
            </p>
            <div className="onboarding-actions">
              <button className="ghost" onClick={back}>
                Back
              </button>
              <span className="spacer" />
              <button className="primary" onClick={next}>
                Next
              </button>
            </div>
          </>
        )}

        {id === "pipeline" && (
          <>
            <h2>Pipeline &amp; review</h2>
            <p>
              Ambiguous catalog fields land in the Review Queue. Tap an answer, then re-run the
              pipeline so human overrides stick — and never get asked again.
            </p>
            <div className="onboarding-actions">
              <button className="ghost" onClick={back}>
                Back
              </button>
              <span className="spacer" />
              <button className="primary" onClick={next}>
                Next
              </button>
            </div>
          </>
        )}

        {id === "chat" && (
          <>
            <h2>How to chat</h2>
            <p>
              Pick a country in the header (prices bind to that currency). Start with something like
              “I run a small salon and drowning in appointment calls”, then narrow — “under 2000 a
              month”. Requirements accumulate; the bot only quotes prices from product cards.
            </p>
            <div className="onboarding-actions">
              <button className="ghost" onClick={back}>
                Back
              </button>
              <span className="spacer" />
              <button className="primary" onClick={next}>
                Next
              </button>
            </div>
          </>
        )}

        {id === "debug" && (
          <>
            <h2>Retrieval panel</h2>
            <p>
              The main pane shows shortlisted recommendations, ranked retrieval hits, and turn
              phases — inspect what would be injected into a sales-agent prompt and why.
            </p>
            <div className="onboarding-actions">
              <button className="ghost" onClick={back}>
                Back
              </button>
              <span className="spacer" />
              <button className="primary" onClick={finish}>
                Enter app
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
