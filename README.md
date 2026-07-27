# Prism

**Talk to your HybridShelf.** Local product chatbot with a normalization pipeline, hybrid Qdrant search, and a developer debug panel.

**Stack:** React (Vite) · FastAPI · Qdrant · OpenAI `gpt-5.4-mini` (normalize / query understanding / chat) · `text-embedding-3-small` (dense) · sparse BM25-style vectors

## Setup

```bash
# 1. Qdrant
docker compose up -d

# 2. Env
cp .env.example .env
# set OPENAI_API_KEY in .env
# optional: set LANGSMITH_API_KEY for AI trace logging (project: prism)

# 3. Backend
cd backend
uv sync
uv run python -m app.pipeline.generate_synthetic
uv run python -m app.pipeline.run_pipeline
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

Health check: http://localhost:8001/health

## Demo script

1. Open **Review Queue**, resolve 1–2 flags (tap recommended or enter free text), click **Re-run pipeline**.
2. Switch to **Chat**, country **IN**.
3. Message: `i am looking for a commercial place near vaishnodevi`
4. Watch the debug panel: filters extracted (`Commercial/Offices` or `Commercial/Retail`), hybrid hits, injected prompt.
5. Follow up: `keep it under 20000000`
6. Watch filters accumulate + INR price bind; bot pitches 2–3 cards.
7. Ask: `what's the size and parking like?` — answered from injected `plan_features`.
8. Try residential: `show me 2 bhk near gift city` — should return apartments, not offices.

## Verify gates (quick)

| Phase | Check |
|---|---|
| 1 | `curl localhost:6333/collections`, `curl localhost:8001/health`, UI two panes |
| 2 | Synthetic JSONL validates; `defect_manifest.json` counts match |
| 3 | Pipeline summary prints `flag_metrics`; Qdrant point count ≈ canonical |
| 4–6 | 3-turn salon conversation; debug tabs populated |
| 7 | Override → rerun → flag not re-asked |

## Notes

- Set a real `OPENAI_API_KEY` in `.env` to use `gpt-5.4-mini` for normalize / chat. If the key is missing or still the placeholder, the app falls back to a heuristic normalizer + hash embeddings so the demo still runs locally.
- **LangSmith:** set `LANGSMITH_API_KEY` (and optionally `LANGSMITH_PROJECT`, default `prism`). When present, OpenAI chat/embedding calls are wrapped and sent to LangSmith. Without the key, the app runs normally with tracing off. Check `/health` → `langsmith_key_present`.
- Backend defaults to port **8001** (see `vite.config.ts` proxy). Port 8000 is often blocked on Windows.
- Qdrant: `docker compose up -d` or any local Qdrant on `QDRANT_URL` (default `http://localhost:6333`).
- First UI visit runs a guided onboarding (setup checklist → how to use). Replay via **Replay tour** in the top bar.
