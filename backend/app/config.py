"""Scoring configuration — the single source of truth for the health model.

P1 (explainability): the score is BASELINE + the signed sum of every feature's
weight. Because it is purely additive, the factors always reconcile to the
displayed number. Weights live here as config, not scattered in code, so a
change is a new MODEL_VERSION (see scoring.py) and never a silent edit.

These are a tunable v1 rubric, not learned weights. Phase 3 would calibrate
them against real renewal/churn outcomes while keeping this additive form.
"""

MODEL_VERSION = "v1"

# Where every account starts before its signals move it.
BASELINE = 72

# --- Feature weights (signed contributions) ---
# Product usage, per module, from NSM attainment tier. Lagging.
MODULE_WEIGHT = {"high": 3, "medium": -4, "low": -9}

# Support health from reopen/escalation behaviour. Leading.
SUPPORT_WEIGHT = {"clean": 3, "elevated": -5, "spiking": -10}

# Relationship strength. Leading.
CHAMPION_WEIGHT = {"engaged": 2, "at_risk": -5, "vacant": -8}

# Survey standing from NPS. Lagging.
SURVEY_WEIGHT = {"strong": 3, "soft": -3, "detractor": -7}

# Billing friction (failed payment / downgrade). Leading.
BILLING_WEIGHT = {"clean": 0, "friction": -6}

# --- Band thresholds (P4: RAG mapping lives in exactly one place) ---
BAND_GREEN_MIN = 80          # score >= 80  -> green
BAND_AMBER_MIN = 55          # 55..79       -> amber, else red

# --- NSM definitions & usage-tier cutoffs (P3) ---
MODULES = {
    "payroll":   {"name": "Payroll",             "nsm": "Payroll runs completed error-free"},
    "workforce": {"name": "Workforce",           "nsm": "Attendance & shift cycles auto-processed"},
    "ee":        {"name": "Employee experience", "nsm": "Review cycles closed with sign-off"},
}
MODULE_ORDER = ["payroll", "workforce", "ee"]

# % of benchmark NSM attainment -> tier
TIER_HIGH_MIN = 85           # > 85%  -> high
TIER_MEDIUM_MIN = 50         # 50-85% -> medium, else low


def band_for(score: int) -> str:
    if score >= BAND_GREEN_MIN:
        return "green"
    if score >= BAND_AMBER_MIN:
        return "amber"
    return "red"


def tier_for(attainment_pct: float) -> str:
    if attainment_pct > TIER_HIGH_MIN:
        return "high"
    if attainment_pct >= TIER_MEDIUM_MIN:
        return "medium"
    return "low"


# tier -> RAG (P4: usage tier and module colour are the same verdict)
TIER_RAG = {"high": "green", "medium": "amber", "low": "red"}


# ---------- Top-3 actions: priority function + LLM (see insights.py, ai.py) ----------
# priority = severity x timing x renewal x actionability; only surface >= floor.
SEVERITY = {"red": 3.0, "amber": 2.0, "green": 1.0}
TIMING_WEIGHT = {"Leading": 1.5, "Lagging": 1.0}
RENEWAL_MULT = [(2, 1.5), (4, 1.2)]          # (<= months to renewal, multiplier); else 1.0
ACTIONABILITY = {                             # by playbook play class
    "quick_win": 1.0, "operational": 0.9, "strategic": 0.8,
    "monitor": 0.5, "upside": 0.6, "none": 0.0,
}
MATERIALITY_FLOOR = 3.0                        # below this, an item is not worth an action
MAX_ACTIONS = 3

# LLM (behind ai.LLMProvider; OpenRouter). Model id is config, per our decision.
LLM_MODEL = "google/gemini-2.5-flash-lite"    # cheapest tier; promote to -flash/haiku if hide-rate high
LLM_TEMPERATURE = 0.2                          # low for consistency across AMs
LLM_MAX_TOKENS = 600
