"""Feature layer + additive scoring engine.

This is the heart of the product. It turns raw input rows (module usage,
metrics) into named features, each with a signed impact, then sums them from
the baseline to a 0-100 score and a RAG band. Every feature it emits becomes a
`score_factor` row, which is exactly what the deep-dive's "Why this score"
panel renders — the panel is the audit trail of this computation, sorted by
absolute impact.
"""
from __future__ import annotations

from . import config as C


def _survey_bucket(nps: int) -> str:
    if nps >= 40:
        return "strong"
    if nps >= 10:
        return "soft"
    return "detractor"


def compute(account: dict, modules: list[dict], metric: dict) -> tuple[int, str, list[dict]]:
    """Return (score, band, factors) for one account.

    account: accounts row
    modules: this account's module_usage rows (with attainment_pct)
    metric:  this account's metrics row
    """
    factors: list[dict] = []

    def add(signal, category, timing, impact, detail, icon):
        factors.append({
            "signal": signal, "category": category, "timing": timing,
            "impact": impact, "detail": detail, "icon": icon,
        })

    # --- Product usage: one factor per module (lagging) ---
    for m in modules:
        key = m["module"]
        name = C.MODULES[key]["name"]
        nsm = C.MODULES[key]["nsm"]
        pct = float(m["nsm_attainment_pct"])
        tier = C.tier_for(pct)
        if tier == "high":
            add(f"{name} usage steady at High", "Product usage", "Lagging",
                C.MODULE_WEIGHT["high"],
                f"{nsm} holding above 85% of benchmark NSM attainment.", "trending-up")
        elif tier == "medium":
            add(f"{name} usage slipped High→Medium", "Product usage", "Lagging",
                C.MODULE_WEIGHT["medium"],
                f"{nsm} fell to 50–85% of benchmark — watch for further decline.", "activity")
        else:
            add(f"{name} usage tier dropped to Low", "Product usage", "Lagging",
                C.MODULE_WEIGHT["low"],
                f"{nsm} now at <50% of benchmark NSM attainment over the last 30 days.", "trending-down")

    # --- Support health (leading) ---
    state = metric.get("support_state", "clean")
    if state == "spiking":
        add("Support tickets spiking", "Support", "Leading", C.SUPPORT_WEIGHT["spiking"],
            "Multiple tickets in the last 7 days with reopens — reopens are a leading risk signal.", "life-buoy")
    elif state == "elevated":
        add("Ticket reopens trending up", "Support", "Leading", C.SUPPORT_WEIGHT["elevated"],
            "Reopened tickets this month vs none last month.", "life-buoy")
    else:
        add("Clean support record", "Support", "Leading", C.SUPPORT_WEIGHT["clean"],
            "No reopened tickets in 60 days; resolutions within SLA.", "life-buoy")

    # --- Relationship / champion (leading) ---
    champ = metric.get("champion_status", "engaged")
    champ_name = account.get("champion", "")
    if champ == "vacant":
        add("Champion left company", "Relationship", "Leading", C.CHAMPION_WEIGHT["vacant"],
            "Primary champion no longer at the account; no replacement identified yet.", "user-x")
    elif champ == "at_risk":
        add("Champion at-risk", "Relationship", "Leading", C.CHAMPION_WEIGHT["at_risk"],
            f"{champ_name} flagged as at-risk / reduced engagement.", "user-x")
    else:
        add("Engaged champion", "Relationship", "Leading", C.CHAMPION_WEIGHT["engaged"],
            f"{champ_name} actively engaged; attended the last QBR.", "user-check")

    # --- Billing friction (leading) ---
    if metric.get("billing_state") == "friction":
        add("Billing friction", "Billing", "Leading", C.BILLING_WEIGHT["friction"],
            "A failed payment and/or downgrade enquiry logged this cycle.", "credit-card")

    # --- Survey standing (lagging) ---
    nps = int(metric["nps"])
    csat = float(metric["csat"])
    bucket = _survey_bucket(nps)
    label = {"strong": "strong", "soft": "soft", "detractor": "detractor"}[bucket]
    add(f"NPS {label}", "Surveys", "Lagging", C.SURVEY_WEIGHT[bucket],
        f"Latest NPS {nps}, CSAT {csat}/5 from post-ticket surveys.", "gauge")

    # --- Sum to score & band ---
    raw = C.BASELINE + sum(f["impact"] for f in factors)
    score = max(0, min(100, raw))
    band = C.band_for(score)

    # Most impactful first (P1: this is the display order too)
    factors.sort(key=lambda f: abs(f["impact"]), reverse=True)
    return score, band, factors
