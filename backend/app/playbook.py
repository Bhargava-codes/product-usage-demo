"""The CS playbook — the closed set of plays the top-3 can recommend.

Single source of truth. `PLAY_IDS` becomes the enum in the LLM's response
schema, so the model is *structurally* unable to invent an off-playbook action
(Gemini structured-output enum constraint). Owned/versioned by CS; the LLM only
selects + phrases from here.

Each play:
  class       -> feeds ACTIONABILITY weight in the priority function
  triggers    -> which factor signals map to this play (substring match)
  collapses   -> factor signals this play *absorbs* as symptoms of one cause
                 (only sanctioned links; keeps root-cause collapse honest)
"""

PLAYBOOK_VERSION = "v1"

PLAYS = {
    "recruit_champion": {
        "class": "strategic",
        "title": "Recruit a new champion / multi-thread to the economic buyer",
        "owner": "AM + manager",
        "triggers": ["Champion left", "Champion at-risk"],
        "collapses": [],
    },
    "build_renewal_save_plan": {
        "class": "strategic",
        "title": "Build a renewal save plan and loop in your manager",
        "owner": "AM + manager",
        "triggers": [],                       # triggered by renewal-near + red band (insights.py)
        "collapses": [],
    },
    "escalate_support_defect": {
        "class": "operational",
        "title": "Escalate the open defect, get a fix ETA, and brief the account",
        "owner": "AM + Support lead",
        "triggers": ["Support tickets spiking", "Ticket reopens"],
        # a support defect commonly depresses usage and NPS — sanctioned collapse:
        "collapses": ["usage tier dropped to Low", "usage slipped", "NPS detractor"],
    },
    "drive_module_adoption": {
        "class": "operational",
        "title": "Diagnose the adoption blocker and run an enablement session",
        "owner": "AM + CSM",
        "triggers": ["usage tier dropped to Low"],
        "collapses": [],
    },
    "resolve_billing": {
        "class": "quick_win",
        "title": "Resolve the failed payment with finance before it compounds",
        "owner": "AM + Finance",
        "triggers": ["Billing friction"],
        "collapses": [],
    },
    "close_survey_loop": {
        "class": "quick_win",
        "title": "Close the loop on the survey detractor's feedback",
        "owner": "AM",
        "triggers": ["NPS detractor", "NPS soft"],
        "collapses": [],
    },
    "monitor_usage_slip": {
        "class": "monitor",
        "title": "Keep a light-touch watch on the slipping module",
        "owner": "AM",
        "triggers": ["usage slipped High"],
        "collapses": [],
    },
    "expand_or_advocate": {
        "class": "upside",
        "title": "Pursue expansion or a reference while the account is strong",
        "owner": "AM",
        "triggers": ["usage steady at High", "NPS strong", "Engaged champion"],
        "collapses": [],
    },
    "no_action": {
        "class": "none",
        "title": "No action needed — the account is stable",
        "owner": "AM",
        "triggers": [],
        "collapses": [],
    },
}

PLAY_IDS = list(PLAYS.keys())   # -> response-schema enum
