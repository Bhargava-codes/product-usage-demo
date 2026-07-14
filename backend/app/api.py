"""FastAPI read API + AI endpoint, and it serves the static frontend.

Altitude-aware (P5): /portfolio is a lean aggregate read, /accounts/{id} is a
rich per-account read. All reads go through the CSV data layer. RBAC is stubbed
here (single-user personal project) — the seam to scope by am_id/manager_id is
marked below.
"""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import ai
from . import config as C
from . import data as D

app = FastAPI(title="Customer Health Platform")

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")

SENTIMENT = {
    "green": {"label": "Positive", "direction": "up"},
    "amber": {"label": "Neutral", "direction": "flat"},
    "red": {"label": "Negative", "direction": "down"},
}
TIER_LABEL = {"high": "High usage", "medium": "Medium usage", "low": "Low usage"}
TIER_ATTAIN = {"high": ">85%", "medium": "50–85%", "low": "<50%"}
TIER_TREND = {"high": "stable", "medium": "declining", "low": "declining"}


# ---------- data helpers (would be a DB query layer in production) ----------
def _accounts_by_id() -> dict[str, dict]:
    return {a["id"]: a for a in D.read("accounts")}


def _latest_snapshots() -> dict[str, dict]:
    """Most recent health_score row per account."""
    latest: dict[str, dict] = {}
    for s in D.read("health_score"):
        aid = s["account_id"]
        if aid not in latest or s["as_of"] > latest[aid]["as_of"]:
            latest[aid] = s
    return latest


def _modules_for(aid: str) -> list[dict]:
    out = []
    for m in D.read("module_usage"):
        if m["account_id"] != aid:
            continue
        pct = float(m["nsm_attainment_pct"])
        tier = C.tier_for(pct)
        key = m["module"]
        out.append({
            "key": key, "name": C.MODULES[key]["name"], "nsm": C.MODULES[key]["nsm"],
            "attainment_pct": pct, "tier": tier, "rag": C.TIER_RAG[tier],
        })
    order = {k: i for i, k in enumerate(C.MODULE_ORDER)}
    out.sort(key=lambda m: order.get(m["key"], 99))
    return out


def _metrics_by_id() -> dict[str, dict]:
    return {m["account_id"]: m for m in D.read("metrics")}


def _factors_for(snapshot_id: str) -> list[dict]:
    rows = [f for f in D.read("score_factor") if f["health_score_id"] == snapshot_id]
    for f in rows:
        f["impact"] = int(f["impact"])
    rows.sort(key=lambda f: abs(f["impact"]), reverse=True)
    return rows


def _fmt_date(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%b %d")
    except ValueError:
        return iso


def _scope(rows: list[dict]) -> list[dict]:
    """RBAC seam: in production, filter to the caller's book here."""
    return rows


# ---------- portfolio ----------
def _portfolio_rows(am: str | None, manager: str | None, q: str | None) -> list[dict]:
    accounts = _scope(D.read("accounts"))
    snaps = _latest_snapshots()
    metrics = _metrics_by_id()
    ql = (q or "").strip().lower()
    out = []
    for a in accounts:
        if am and am != "all" and a["am"] != am:
            continue
        if manager and manager != "all" and a["manager"] != manager:
            continue
        if ql and ql not in a["name"].lower() and ql not in a["industry"].lower():
            continue
        snap = snaps.get(a["id"])
        if not snap:
            continue
        met = metrics.get(a["id"], {})
        mods = _modules_for(a["id"])
        band = snap["band"]
        out.append({
            "id": a["id"], "name": a["name"], "industry": a["industry"], "am": a["am"],
            "manager": a["manager"],
            "score": int(snap["score"]), "band": band,
            "sentiment": SENTIMENT[band],
            "modules": {m["key"]: m["rag"] for m in mods},
            "nps": int(met.get("nps", 0)), "csat": float(met.get("csat", 0)),
        })
    out.sort(key=lambda r: r["score"])
    return out


@app.get("/api/filters")
def filters():
    accounts = _scope(D.read("accounts"))
    ams = sorted({a["am"] for a in accounts})
    mgrs = sorted({a["manager"] for a in accounts})
    return {"ams": ams, "managers": mgrs}


@app.get("/api/portfolio")
def portfolio(am: str | None = None, manager: str | None = None, q: str | None = None):
    rows = _portfolio_rows(am, manager, q)
    # module-health matrix counts over the same filtered set (P: counts stay stable)
    counts = {k: {"red": 0, "amber": 0, "green": 0} for k in C.MODULE_ORDER}
    for r in rows:
        for k, rag in r["modules"].items():
            counts[k][rag] += 1
    matrix = [{"key": k, "name": C.MODULES[k]["name"], **counts[k]} for k in C.MODULE_ORDER]
    return {"accounts": rows, "count": len(rows), "matrix": matrix}


# ---------- account deep-dive ----------
def _deep_dive(aid: str) -> dict:
    accounts = _accounts_by_id()
    if aid not in accounts:
        raise HTTPException(404, "account not found")
    a = accounts[aid]
    snap = _latest_snapshots().get(aid)
    met = _metrics_by_id().get(aid, {})
    mods = _modules_for(aid)
    factors = _factors_for(snap["id"])
    band = snap["band"]
    champ_status = met.get("champion_status", "engaged")
    return {
        "id": aid, "name": a["name"], "industry": a["industry"],
        "am": a["am"], "manager": a["manager"], "arr": a["arr"],
        "renewal_date": a["renewal_date"], "champion": a["champion"],
        "champion_status": champ_status, "champion_ok": champ_status == "engaged",
        "score": int(snap["score"]), "band": band, "model_version": snap["model_version"],
        "sentiment": SENTIMENT[band],
        "nps": int(met.get("nps", 0)), "csat": float(met.get("csat", 0)),
        "factors": factors,
        "modules": [{
            "key": m["key"], "name": m["name"], "nsm": m["nsm"], "rag": m["rag"],
            "tier": m["tier"], "tier_label": TIER_LABEL[m["tier"]],
            "attain": TIER_ATTAIN[m["tier"]], "trend": TIER_TREND[m["tier"]],
        } for m in mods],
    }


@app.get("/api/accounts/{aid}")
def account(aid: str):
    return _deep_dive(aid)


@app.get("/api/accounts/{aid}/timeline")
def timeline(aid: str, type: str | None = None):
    rows = [s for s in D.read("signals") if s["account_id"] == aid]
    if type and type != "all":
        rows = [s for s in rows if s["type"] == type]
    rows.sort(key=lambda s: s["occurred_at"], reverse=True)
    present = sorted({s["type"] for s in D.read("signals") if s["account_id"] == aid})
    return {
        "events": [{
            "date": _fmt_date(s["occurred_at"]), "occurred_at": s["occurred_at"],
            "type": s["type"], "title": s["title"], "detail": s["detail"],
        } for s in rows],
        "types": present,
    }


@app.get("/api/accounts/{aid}/trend")
def trend(aid: str):
    rows = [s for s in D.read("health_score") if s["account_id"] == aid]
    rows.sort(key=lambda s: s["as_of"])
    points = [{"as_of": s["as_of"],
               "label": datetime.strptime(s["as_of"], "%Y-%m-%d").strftime("%b"),
               "score": int(s["score"]), "band": s["band"]} for s in rows]
    delta = points[-1]["score"] - points[0]["score"] if points else 0
    return {"points": points, "delta": delta,
            "current": points[-1]["score"] if points else 0,
            "band": points[-1]["band"] if points else "amber"}


# ---------- top-3 actions (deterministic candidates + LLM select/phrase) ----------
@app.get("/api/accounts/{aid}/actions")
def actions(aid: str):
    accounts = _accounts_by_id()
    if aid not in accounts:
        raise HTTPException(404, "account not found")
    a = accounts[aid]
    snap = _latest_snapshots().get(aid)
    factors = _factors_for(snap["id"])
    result = ai.recommend_actions(a, snap["band"], int(snap["score"]), factors)
    if result is None:
        # validation failed -> hide the section (the factor panel remains)
        return Response(status_code=204)
    return result


# ---------- static frontend ----------
@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
