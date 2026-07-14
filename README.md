# Unified Customer Health Platform

An internal Account-Manager tool that fuses six disconnected signal streams
(product usage, support, CRM, surveys, billing, relationship) into one
**explainable, near-real-time account-health view** — surfaced early enough to
act on renewal risk before the renewal call.

This is a runnable personal-project build of the [design & backend plan]. Data
is stored as **CSV files** (per the project decision); the health score and its
factor breakdown are **computed by an additive engine**, not hard-coded.

```
┌── frontend/            no-build React app (served by FastAPI)
│     index.html         portfolio · deep-dive · AI drawer
└── backend/
      app/
        config.py        scoring weights, bands, NSM defs  ← the model
        data.py          CSV read/write layer (the "DB")
        scoring.py       feature layer + additive scoring engine
        ai.py            provider-agnostic LLM seam + context assembler
        seed.py          generate sample CSVs + compute snapshots
        api.py           FastAPI read API + AI endpoint + static frontend
      data/*.csv         generated tables (git-ignored)
```

## Run it

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed                       # generate & score the sample data
uvicorn app.api:app --port 8077          # then open http://127.0.0.1:8077
```

The frontend loads React, Babel, and Lucide from a CDN (no Node/npm needed).
Install Node later and it ports to Vite cleanly.

## How the score works (P1: never a black box)

`score = clamp₀₋₁₀₀(BASELINE + Σ weightᵢ)` — a purely additive model, so the
factors always reconcile to the number shown. Each feature emits one
`score_factor` row, which is exactly what the deep-dive's "Why this score"
panel renders, sorted by absolute impact.

Bands (P4, one place): green ≥ 80 · amber 55–79 · red < 55.
Usage tiers (P3, from NSM attainment %): high > 85 · medium 50–85 · low < 50.

Weights live in `app/config.py` as a **versioned v1 rubric** — tune them there;
a change should bump `MODEL_VERSION`. They are illustrative, not learned.

## Data model (CSV tables)

| File | Kind | Columns |
|------|------|---------|
| `accounts.csv` | input | id, name, industry, am, manager, arr, renewal_date, champion |
| `module_usage.csv` | input | account_id, module, nsm_attainment_pct |
| `metrics.csv` | input | account_id, nps, csat, support_state, champion_status, billing_state |
| `signals.csv` | input | account_id, occurred_at, type, title, detail, source |
| `health_score.csv` | computed | id, account_id, as_of, score, band, model_version |
| `score_factor.csv` | computed | health_score_id, account_id, signal, category, timing, impact, detail, icon |

`signal` is both a timeline row and a scoring input. `health_score` is
append-only immutable snapshots — the month-over-month trend is just a query
over them.

## Wiring a real LLM (currently abstracted, P6)

The AI drawer ships with a deterministic `CannedProvider` so it works with
nothing external. To go live, implement `LLMProvider.complete` in `app/ai.py`
(e.g. an Anthropic adapter reading `ANTHROPIC_API_KEY`) and set `_provider`.
The route, the server-side context assembler, and the guardrails don't change —
that seam is what keeps "use ONLY this data, never invent numbers" enforceable.

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/portfolio?am=&manager=&q=` | accounts + module-health matrix |
| `GET /api/accounts/{id}` | deep-dive: score, factors, module tiers |
| `GET /api/accounts/{id}/timeline?type=` | unified timeline |
| `GET /api/accounts/{id}/trend` | month-over-month snapshots |
| `POST /api/accounts/{id}/ai/messages` | account-scoped AI |
| `GET /api/filters` | AM / manager options |

## Not yet built (see the plan)

Real source connectors, the alerts engine, RBAC scoping (stubbed in
`api._scope`), and Phase-3 ML weight calibration.
