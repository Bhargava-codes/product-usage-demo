# Unified Customer Health Platform
Prod link - https://product-usage-demo.onrender.com

An internal Account-Manager tool that fuses six disconnected signal streams
(product usage, support, CRM, surveys, billing, relationship) into one
**explainable, near-real-time account-health view** — surfaced early enough to
act on renewal risk before the renewal call.

Data is stored as **CSV files**; the health score and its factor breakdown are
**computed by an additive engine**, not hard-coded. A cheap LLM sits on top —
but only to *narrate* and to *select next-actions from a closed playbook*, never
to compute anything authoritative.

---

## Product decisions (the AI-PM cut)

This project is as much about *where not to use an LLM* as where to use one. The
decisions that shaped it:

1. **The engine owns the truth; the LLM only narrates it.** The score and its
   "Why this score" factors are a purely additive, fully-auditable computation.
   An LLM-written score could never *guarantee* the words match the math, so the
   model is kept off anything authoritative. Explainability is a hard constraint,
   not a nice-to-have.
2. **Recommended actions are playbook-grounded, not invented.** Actions are
   selected from a closed CS playbook whose IDs form a **response-schema enum** —
   so the model is *structurally* unable to emit an off-playbook action. A
   validator then checks the model cited only real signals; on any failure the
   section hides and the deterministic factor panel remains.
4. **The hard judgement is deterministic.** Symptom→cause collapse (e.g. a support
   defect that's dragging usage *and* NPS down becomes **one** action) and the
   priority ranking (severity × timing × renewal-proximity × actionability) run in
   code. The LLM only selects ≤3 and phrases them — a bounded selector, not an
   author.
5. **Built to be eval-gated.** The LLM path ships behind a materiality floor,
   validation, and a hide-on-failure fallback, so it can be trusted only after an
   eval set measures its grounding and on-playbook rate.

The prompt itself follows Google's documented Gemini guidance (persona +
constraints in the system instruction, XML-tag delimiters, few-shot examples,
schema supplied via `response_format` rather than duplicated in the prompt).

---

## Architecture

```
┌── frontend/            no-build React app (served by FastAPI)
│     index.html         portfolio · account deep-dive · top-actions card
└── backend/
      app/
        config.py        scoring weights, bands, NSM defs, priority weights ← the model
        data.py          CSV read/write layer (the "DB")
        scoring.py       feature layer + additive scoring engine
        insights.py      deterministic what-changed diff + priority ranking + symptom→cause collapse
        playbook.py      the closed CS playbook (its IDs become the LLM's schema enum)
        ai.py            provider-agnostic LLM seam + OpenRouter provider + validation
        api.py           FastAPI read API + /actions endpoint + static frontend
        seed.py          generate sample CSVs + compute snapshots
      prompts/
        top3_actions.system.md   system prompt (Gemini-tuned, cache-split)
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

## Deploy (one service, free tier)

The repo ships a `render.yaml` blueprint and a `Procfile`. On a fresh deploy the
app **auto-seeds and scores the sample data on startup** (the CSVs are
git-ignored), so there are no manual steps. On [Render](https://render.com):
New → Blueprint → connect this repo → Apply. That's it — the service builds,
boots, seeds, and serves the full UI. (Free instances cold-start in ~30–50s
after idle.) Set `OPENROUTER_API_KEY` in the dashboard to also enable the LLM
layer; without it the deterministic playbook path runs.

**Optional — turn on the LLM layer:** the top-actions card runs on a deterministic
playbook by default. Export an OpenRouter key *in the same shell before starting
the server* and it will additionally generate the one-line summary and tailor the
action wording (`google/gemini-2.5-flash-lite` by default, set in `config.py`):

```bash
export OPENROUTER_API_KEY=...            # your key; read from env only, never stored
```

## How the score works

`score = clamp₀₋₁₀₀(BASELINE + Σ weightᵢ)` — a purely additive model, so the
factors always reconcile to the number shown. Each feature emits one
`score_factor` row, which is exactly what the deep-dive's "Why this score" panel
renders, sorted by absolute impact.

Bands (one place): green ≥ 80 · amber 55–79 · red < 55.
Usage tiers (from NSM attainment %): high > 85 · medium 50–85 · low < 50.
Weights live in `app/config.py` as a **versioned v1 rubric** — illustrative, not learned.

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

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/portfolio?am=&manager=&q=` | accounts + module-health matrix |
| `GET /api/accounts/{id}` | deep-dive: score, factors, module tiers |
| `GET /api/accounts/{id}/timeline?type=` | unified timeline |
| `GET /api/accounts/{id}/trend` | month-over-month snapshots |
| `GET /api/accounts/{id}/actions` | what-changed diff + top-3 grounded actions |
| `GET /api/filters` | AM / manager options |

## Not yet built (deliberately)

Real source connectors, the alerts engine, RBAC scoping (stubbed in
`api._scope`), an eval harness to gate the LLM path, and Phase-3 ML weight
calibration.
