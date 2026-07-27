# Conversation Summary — Product Filtering & RAG for Chatbot

**Date:** 2026-07-20
**Goal:** Design a mechanism that identifies a user's requirement mid-chat, retrieves relevant products from a catalog of a few thousand items (too large for prompt injection), and injects only the relevant ones into the chatbot prompt.

---

## 1. Problem Statement

- Catalog: a few thousand products, each with multiple variations/plans.
- Cannot inject the full catalog into the LLM prompt.
- Core blocker: (a) understand the user's requirement from an ongoing conversation, (b) search relevant products, (c) inject them into the chatbot prompt — all in real time.

## 2. Requirements Discovered (via Q&A)

| Question | Answer |
|---|---|
| Query style | **Mixed** — both attribute/spec-based and vague/need-based |
| Data structure | **Mix** — some structured attributes + free-text descriptions |
| Stack constraint | **Nothing yet, flexible** → later fixed: **Qdrant** as vector DB |
| Product nature (from admin UI screenshots) | Service/SaaS-style offerings: Basic Details (name, category, KB article, unit, description), **per-country/currency Price Lists** (amount, discount, discount strategy), and **Plans** as variations |

### Still open (explicitly unresolved — do not assume)
1. **Source system** for extraction: own Postgres/admin DB behind the Create Product form, or a third-party platform?
2. **Plans recurring vs one-time?** Determines whether `billing_period` is mandatory in the price structure.
3. **Is the user's country known at chat start** (account/locale), or must the bot ask before quoting prices?
4. Catalog change cadence (prices/stock) → nightly cron vs webhook-driven fast-lane.
5. Single business (2–3 categories) vs marketplace-style multi-industry → how far to invest in vocabulary governance.

## 3. Architecture Decisions

### 3.1 Retrieval strategy
- **Not** pure vector RAG. Chosen pattern: **LLM query understanding → hard structured filters → hybrid (sparse + dense) rank within the filtered set → inject top-N compact cards.**
- Embeddings must never handle numeric/hard constraints (price, availability) — those are Qdrant payload filters.
- Query-understanding LLM call sees **full conversation history** (filters accumulate across turns; "show me cheaper ones" needs context) and rewrites cumulative intent into fresh filters each turn.
- Chatbot exposes a `search_products` tool (agentic single-loop) rather than a forced two-call pipeline — handles turns that need no search.

### 3.2 Vector store: Qdrant
- One point per **parent product** (never per variation/plan — avoids near-duplicate pollution of top-K).
- **Named vectors**: `dense` (embedding model) + `sparse` (BM25/SPLADE); server-side RRF fusion via Qdrant Query API.
- **Payload** carries everything needed for filtering + display: prices (nested per-country array), plans, attributes, `status`, `review_pending`, `content_hash`, precomputed `display_card`.
- Explicit **payload indexes** on every filterable field (Qdrant does not auto-index).
- Qdrant is the **serving store, not system of record** — always rebuildable from canonical data. Full rebuilds → new collection + **alias swap** (`products_live`) for zero downtime.
- Price/stock-only changes → `set_payload` fast lane, no re-embedding.

### 3.3 Universal schema — three layers
A fully universal flat schema is impossible ("size" means different things per industry). Adopted the marketplace-standard hybrid:

1. **Universal core** (strict, fixed): `id`, `kind` (physical_good | digital_good | service | subscription | bundle), `title`, `brand_or_provider`, `category_path`, `clean_description`, `use_case_tags`, `price_min/max` + currency, `availability`, `status`, `offerings[]` (generalizes variations/plans/tiers).
2. **Typed block per `kind`**: e.g. services get `duration_minutes`, `location_mode`, `scheduling_required`.
3. **Namespaced attributes** (`footwear.color`, `automation.integrations`) governed by **per-category vocabulary files** — new industries = new YAML vocabulary, not new code.

Tradeoffs accepted: complexity moves into vocabulary governance; cross-category comparison stays shallow; category assignment becomes load-bearing (strictest review threshold on `cant_categorize`).

### 3.4 Fields recommended beyond the current admin form
- **Tier 1 (retrieval-critical):** `use_case_tags`, `target_audience`, per-plan structured `features[]`, `status`, `billing_period` (if recurring).
- **Tier 2 (cheap now, painful later):** immutable external ID/slug, hierarchical category, `aliases[]`, `short_pitch`.
- **Tier 3 (situational):** prerequisites/compatibility, related products, regional availability flags.
- **Warnings:** free-text "Discount Strategy" must be structured (percent/flat + validity) if the bot quotes final prices; multi-currency breaks a single `price_min` — resolve the user's country first, then filter the nested price entry.
- **KB articles = second retrieval layer**: separate chunked Qdrant collection, chunks tagged with `product_id`; product collection answers "which product", KB collection answers deep detail questions filtered to the identified product.

## 4. ETL Pipeline (5 stages, diff-driven, idempotent)

```
0→1 Extract        raw JSONL snapshot, verbatim, per run
1→2 Pre-process    deterministic only: strip HTML, canonicalize (ISO country,
                   currency), resolve plan→price refs, derive price_min/max
                   per currency, validate → dead_letter.jsonl,
                   compute content_hash → unchanged products skip LLM & embed
2→3 Normalize      LLM structured-output call (see §5) → Normalization Record;
                   confidence/flag routing → review_queue / overrides
3→4 Merge          Staged + Normalization + human overrides → Canonical Product
                   (versioned contract) → render embedding text (template, not
                   LLM) + display_card
4→5 Embed & Upsert only changed hashes; dense+sparse named vectors; alias swap
                   on full rebuild; set_payload fast lane for price/stock
```

Post-run integrity check: canonical active count == Qdrant point count + spot queries.

## 5. LLM Normalization Pass

- **Input per product:** semantic fields only (name, raw category, cleaned description, plan names/feature text, unit) — never prices/IDs/URLs — plus controlled vocabularies, minus fields already answered in `overrides/`.
- **Vocabulary built in two passes:** Pass A proposes values from the catalog → human approves canonical list → Pass B normalizes against it.
- **Output (strict JSON, schema-validated, retry once → dead-letter):** `clean_description`, `short_pitch`, `category_path`, `use_case_tags`, `target_audience`, `aliases`, `plan_features{}`, `confidence`, `flags[]`.
- **Flag types:** `ambiguous_attribute`, `contradiction`, `missing_required`, `suspected_duplicate`, `cant_categorize`, `plans_indistinguishable`. Each flag carries `field`, `issue`, `options[]`, `recommended`.
- **Routing:** confidence ≥ 0.85 and no flags → auto-accept; else → review queue rendered as tap-to-answer UI (options + free-text field). Pipeline does not block; flagged items proceed with `recommended` + `review_pending: true`. Human answers persist in version-controlled `overrides/` keyed by product_id — never re-asked, never clobbered.
- **Calibrate early:** run on ~50 products, eyeball auto-accepts, tune prompt to flag only filter-affecting ambiguity.

## 6. Serving Flow (per chat turn)

1. Chatbot (with history) decides whether to call `search_products`.
2. Tool call extracts structured filters + `semantic_query`; code binds currency/country from session (LLM never guesses currency).
3. Qdrant: payload filters → hybrid dense+sparse → RRF → top 10–20.
4. Zero results → relax softest filter (price ±20% / drop soft attribute) and say so. Too many/vague → bot asks one narrowing question.
5. Inject compact `display_card` lines with stable IDs (`[P-1043] …`) → bot pitches, can reference IDs for rich UI cards; KB collection handles follow-up detail questions.

## 7. POC Decisions (final Q&A)

| Decision | Choice |
|---|---|
| Stack | **React + FastAPI** (proper demo: chat UI + live debug panel) |
| Embeddings | **OpenAI/Voyage API** (Anthropic has no embeddings API); chat LLM: Anthropic |
| Catalog data | **Synthetic messy catalog** (deliberately dirty → exercises normalization, flags, review flow) |

POC scope: normalization pipeline, product ETL + RAG, all schemas, chat UI that gathers requirements → RAGs → pitches in ongoing chat, plus a developer debug panel exposing the underlying mindmap/flow. Detailed plan in `02_poc_implementation_plan.md`.
