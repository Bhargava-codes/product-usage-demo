"""Deterministic pre-LLM layer: what-changed + ranked action candidates.

This does the judgement-free work — snapshot diff, the priority function, and
the sanctioned symptom->cause collapse — so the LLM receives a short list of
*already-ranked, playbook-mapped* candidates and only has to select <=3,
tailor the wording, and write the one-line read. Nothing here calls a model.
"""
from __future__ import annotations

from datetime import date

from . import config as C
from . import data as D
from .playbook import PLAYS

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def months_to_renewal(renewal: str, today: date | None = None) -> int:
    """Parse 'Jul 2026' -> whole months from today (large if unparseable)."""
    today = today or date.today()
    try:
        mon, yr = renewal.split()
        m, y = _MONTHS[mon], int(yr)
        return (y - today.year) * 12 + (m - today.month)
    except Exception:
        return 999


def _renewal_mult(months: int) -> float:
    for threshold, mult in C.RENEWAL_MULT:
        if months <= threshold:
            return mult
    return 1.0


def _severity(impact: int) -> float:
    a = abs(impact)
    if a >= 8:
        return C.SEVERITY["red"]
    if a >= 4:
        return C.SEVERITY["amber"]
    return C.SEVERITY["green"]


def _play_for(signal: str) -> str | None:
    for pid, p in PLAYS.items():
        for trig in p["triggers"]:
            if trig.lower() in signal.lower():
                return pid
    return None


def what_changed(account_id: str) -> dict:
    """Diff the two most recent snapshots (deterministic 'what changed')."""
    snaps = sorted((s for s in D.read("health_score") if s["account_id"] == account_id),
                   key=lambda s: s["as_of"])
    if len(snaps) < 2:
        return {"score_delta": 0, "prev_band": None, "band": snaps[-1]["band"] if snaps else None}
    prev, latest = snaps[-2], snaps[-1]
    delta = int(latest["score"]) - int(prev["score"])
    return {
        "score_delta": delta,
        "prev_band": prev["band"], "band": latest["band"],
        "band_changed": prev["band"] != latest["band"],
        "direction": "improving" if delta > 0 else "worsening" if delta < 0 else "flat",
    }


def rank_candidates(factors: list[dict], account: dict, band: str) -> list[dict]:
    """Turn scored factors into a priority-ordered list of playbook candidates.

    factors: the account's score_factor rows (signal, impact, timing, category...)
    Returns candidates (already collapsed, floored, capped) for the LLM to finalise.
    """
    months = months_to_renewal(account.get("renewal_date", ""))
    rmult = _renewal_mult(months)

    # 1) map each *problem* factor (negative impact) to a play, compute priority
    cand: dict[str, dict] = {}
    for f in factors:
        impact = int(f["impact"])
        if impact >= 0:
            continue
        pid = _play_for(f["signal"])
        if not pid:
            continue
        cls = PLAYS[pid]["class"]
        prio = _severity(impact) * C.TIMING_WEIGHT.get(f["timing"], 1.0) * rmult * C.ACTIONABILITY[cls]
        c = cand.setdefault(pid, {"play_id": pid, "title": PLAYS[pid]["title"], "class": cls,
                                  "owner": PLAYS[pid]["owner"], "addresses": [], "priority": 0.0})
        c["addresses"].append(f["signal"])
        c["priority"] = max(c["priority"], prio)

    # 2) sanctioned symptom->cause collapse: a cause play absorbs its symptoms,
    #    and the standalone symptom plays are removed.
    for pid, p in PLAYS.items():
        if pid in cand and p["collapses"]:
            for f in factors:
                if any(link.lower() in f["signal"].lower() for link in p["collapses"]):
                    if f["signal"] not in cand[pid]["addresses"]:
                        cand[pid]["addresses"].append(f["signal"])
                    # drop the standalone play this symptom generated
                    sym = _play_for(f["signal"])
                    if sym and sym != pid and sym in cand:
                        cand.pop(sym, None)

    # 3) renewal-near + red -> add the strategic save-plan candidate
    if band == "red" and months <= C.RENEWAL_MULT[-1][0] + 2:
        cand.setdefault("build_renewal_save_plan", {
            "play_id": "build_renewal_save_plan", "title": PLAYS["build_renewal_save_plan"]["title"],
            "class": "strategic", "owner": PLAYS["build_renewal_save_plan"]["owner"],
            "addresses": [f"Renewal in ~{max(months,0)} months while {band.upper()}"],
            "priority": 3.0 * rmult * C.ACTIONABILITY["strategic"],
        })

    # 4) materiality floor + cap
    ranked = sorted((c for c in cand.values() if c["priority"] >= C.MATERIALITY_FLOOR),
                    key=lambda c: c["priority"], reverse=True)[:C.MAX_ACTIONS]

    # 5) healthy account: nothing material -> upside or no-action
    if not ranked:
        if band == "green":
            ranked = [{"play_id": "expand_or_advocate", "title": PLAYS["expand_or_advocate"]["title"],
                       "class": "upside", "owner": PLAYS["expand_or_advocate"]["owner"],
                       "addresses": ["Account stable / green"], "priority": 0.0}]
        else:
            ranked = [{"play_id": "no_action", "title": PLAYS["no_action"]["title"],
                       "class": "none", "owner": PLAYS["no_action"]["owner"],
                       "addresses": [], "priority": 0.0}]
    return ranked
