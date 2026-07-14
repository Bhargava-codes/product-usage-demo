"""Generate sample CSVs and compute the initial score snapshots.

Writes the INPUT tables (accounts, module_usage, metrics, signals) with the
prototype's 10 fictional accounts, then runs the scoring engine to produce the
COMPUTED tables (health_score snapshots + score_factor breakdowns). Run:

    python -m app.seed
"""
from __future__ import annotations

import random

from . import config as C
from . import data as D
from . import scoring

RAG_PCT = {"green": 90.0, "amber": 68.0, "red": 40.0}  # module RAG -> sample NSM %

# id, name, industry, am, manager, arr, renewal, champion,
# modules(payroll,workforce,ee), nps, csat, support_state, champion_status, billing_state
ACCOUNTS = [
    ("apex", "Apex Consumer Goods", "FMCG", "Priya Nair", "Sneha Iyer", "₹1.4 Cr", "Mar 2027", "Ritu Malhotra",
     ("green", "green", "green"), 62, 4.7, "clean", "engaged", "clean"),
    ("meridian", "Meridian Retail Group", "Retail", "Priya Nair", "Sneha Iyer", "₹92 L", "Nov 2026", "Karan Shah",
     ("green", "green", "amber"), 54, 4.5, "clean", "engaged", "clean"),
    ("solstice", "Solstice Media", "Media", "Aisha Khan", "Arjun Desai", "₹68 L", "Jan 2027", "Neha Kapoor",
     ("green", "green", "green"), 49, 4.6, "clean", "engaged", "clean"),
    ("zephyr", "Zephyr Logistics", "Logistics", "Priya Nair", "Sneha Iyer", "₹1.1 Cr", "Sep 2026", "Amit Verma",
     ("green", "amber", "amber"), 31, 4.1, "elevated", "engaged", "clean"),
    ("lumen", "Lumen Energy", "Energy", "Vikram Rao", "Arjun Desai", "₹84 L", "Oct 2026", "Deepa Rao",
     ("green", "amber", "amber"), 24, 4.0, "elevated", "engaged", "clean"),
    ("northwind", "Northwind Manufacturing", "Manufacturing", "Rahul Menon", "Sneha Iyer", "₹1.6 Cr", "Aug 2026", "Sanjay Gupta",
     ("amber", "green", "amber"), 16, 3.8, "clean", "at_risk", "clean"),
    ("vertex", "Vertex Pharma", "Pharma", "Aisha Khan", "Arjun Desai", "₹1.2 Cr", "Sep 2026", "Meera Joshi",
     ("amber", "amber", "red"), 5, 3.5, "elevated", "at_risk", "friction"),
    ("ironclad", "Ironclad Insurance", "Insurance", "Rahul Menon", "Sneha Iyer", "₹2.1 Cr", "Aug 2026", "(vacant)",
     ("amber", "red", "red"), -8, 3.2, "spiking", "vacant", "friction"),
    ("cobalt", "Cobalt Fintech", "Fintech", "Rahul Menon", "Sneha Iyer", "₹78 L", "Jul 2026", "Vivek Nair",
     ("red", "amber", "red"), -14, 3.0, "spiking", "at_risk", "friction"),
    ("harbor", "Harbor & Co Retail", "Retail", "Vikram Rao", "Arjun Desai", "₹95 L", "Jul 2026", "(vacant)",
     ("red", "red", "amber"), -22, 2.8, "spiking", "vacant", "friction"),
]

# 8 monthly snapshot dates, Dec 2025 -> Jul 2026 (as_of)
MONTHS = ["2025-12-01", "2026-01-01", "2026-02-01", "2026-03-01",
          "2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01"]


def gen_trend(score: int, band: str, rng: random.Random) -> list[int]:
    """Plausible 8-point history ending at the current computed score.

    Sample history only — in production these are real prior computations.
    """
    n = 8
    if band == "red":
        start = min(88, score + 34)
    elif band == "amber":
        start = score + (9 if rng.random() < 0.5 else -6)
    else:
        start = max(60, score - 7)
    arr = []
    for i in range(n):
        t = i / (n - 1)
        v = start + (score - start) * t
        if 0 < i < n - 1:
            v += (4 if i % 2 == 0 else -4) * (1.4 if band == "amber" else 0.7)
        arr.append(max(15, min(99, round(v))))
    arr[-1] = score
    return arr


def gen_signals(acc_id: str, band: str, nps: int, renewal: str, champion: str) -> list[dict]:
    """Unified-timeline events for the account, keyed to its band."""
    ev: list[tuple[str, str, str, str]] = []  # (occurred_at, type, title, detail)
    if band == "red":
        ev = [
            ("2026-07-12", "support", "Escalation bypassed AM", "A support escalation was raised directly to leadership, bypassing the account manager."),
            ("2026-07-09", "billing", "Payment failed", "Monthly invoice auto-charge failed; finance contact notified."),
            ("2026-07-05", "usage", "Payroll runs down 42%", "Successful payroll runs fell to <50% of contracted volume vs the trailing 30-day baseline."),
            ("2026-07-02", "relationship",
             "Champion left company" if champion == "(vacant)" else "Champion disengaged",
             "Primary stakeholder no longer appears in the org; contact record marked vacant." if champion == "(vacant)"
             else f"{champion} declined the last two check-in invites."),
            ("2026-06-28", "support", "2 tickets reopened", "Both reopens concern the same attendance-sync defect."),
            ("2026-06-20", "survey", "NPS detractor response", f"Score {nps} with free-text citing \"too much manual cleanup\"."),
            ("2026-06-08", "sales", "Renewal flagged at-risk", f"AE moved the renewal stage to \"at-risk\" ahead of the {renewal} date."),
        ]
    elif band == "amber":
        ev = [
            ("2026-07-11", "usage", "Workforce usage softening", "Shift-cycle automation slipped to the 50–85% band over 14 days."),
            ("2026-07-06", "support", "Ticket reopened", "A configuration ticket was reopened after an incomplete fix."),
            ("2026-06-30", "survey", "Mixed QBR feedback", "QBR noted value in payroll but frustration with reporting exports."),
            ("2026-06-22", "onboarding", "New module kickoff", "Employee-experience module kickoff call completed with the HR team."),
            ("2026-06-14", "usage", "Payroll steady", "Payroll runs holding above benchmark for the 3rd month."),
            ("2026-06-03", "sales", "Upsell conversation", "AE logged interest in the analytics add-on."),
        ]
    else:
        ev = [
            ("2026-07-10", "advocacy", "Case-study interest", "Champion agreed to participate in a joint case study."),
            ("2026-07-04", "survey", "Promoter NPS", f"Score {nps} — cited fast payroll runs and responsive support."),
            ("2026-06-27", "usage", "All modules High", "Every module holding above 85% NSM attainment."),
            ("2026-06-18", "support", "Fast resolution", "3 tickets, all resolved under SLA, no reopens."),
            ("2026-06-09", "sales", "Expansion booked", "Added 40 seats; ARR uplift recorded."),
            ("2026-05-30", "onboarding", "Rollout complete", "Full onboarding checklist completed ahead of the day-30 target."),
        ]
    return [{"account_id": acc_id, "occurred_at": d, "type": t, "title": ti, "detail": de,
             "source": t} for (d, t, ti, de) in ev]


def run() -> None:
    rng = random.Random(42)
    accounts_rows, module_rows, metric_rows, signal_rows = [], [], [], []
    health_rows, factor_rows = [], []

    for a in ACCOUNTS:
        (aid, name, industry, am, mgr, arr, renewal, champion,
         mods, nps, csat, support, champ_status, billing) = a

        accounts_rows.append({
            "id": aid, "name": name, "industry": industry, "am": am, "manager": mgr,
            "arr": arr, "renewal_date": renewal, "champion": champion,
        })
        acc_modules = []
        for key, rag in zip(C.MODULE_ORDER, mods):
            row = {"account_id": aid, "module": key, "nsm_attainment_pct": RAG_PCT[rag]}
            module_rows.append(row)
            acc_modules.append(row)
        metric = {"account_id": aid, "nps": nps, "csat": csat,
                  "support_state": support, "champion_status": champ_status,
                  "billing_state": billing}
        metric_rows.append(metric)

        # --- run the engine ---
        score, band, factors = scoring.compute(accounts_rows[-1], acc_modules, metric)

        # timeline (band-keyed)
        signal_rows.extend(gen_signals(aid, band, nps, renewal, champion))

        # 8 monthly snapshots; latest is the computed current score
        trend = gen_trend(score, band, rng)
        for as_of, s in zip(MONTHS, trend):
            health_rows.append({
                "id": f"{aid}-{as_of}", "account_id": aid, "as_of": as_of,
                "score": s, "band": C.band_for(s), "model_version": C.MODEL_VERSION,
            })
        # factor breakdown attaches to the latest snapshot only
        latest_id = f"{aid}-{MONTHS[-1]}"
        for f in factors:
            factor_rows.append({
                "health_score_id": latest_id, "account_id": aid,
                "signal": f["signal"], "category": f["category"], "timing": f["timing"],
                "impact": f["impact"], "detail": f["detail"], "icon": f["icon"],
            })
        print(f"  {name:<26} {score:>3}  {band.upper()}")

    D.write("accounts", accounts_rows, ["id", "name", "industry", "am", "manager", "arr", "renewal_date", "champion"])
    D.write("module_usage", module_rows, ["account_id", "module", "nsm_attainment_pct"])
    D.write("metrics", metric_rows, ["account_id", "nps", "csat", "support_state", "champion_status", "billing_state"])
    D.write("signals", signal_rows, ["account_id", "occurred_at", "type", "title", "detail", "source"])
    D.write("health_score", health_rows, ["id", "account_id", "as_of", "score", "band", "model_version"])
    D.write("score_factor", factor_rows, ["health_score_id", "account_id", "signal", "category", "timing", "impact", "detail", "icon"])
    print(f"\nWrote {len(accounts_rows)} accounts, {len(signal_rows)} signals, "
          f"{len(health_rows)} snapshots, {len(factor_rows)} factors -> backend/data/*.csv")


if __name__ == "__main__":
    print("Scoring accounts (model %s, baseline %d):" % (C.MODEL_VERSION, C.BASELINE))
    run()
