"""Account AI layer — provider-agnostic, grounded, structured.

Not a chatbot. One bounded job: given an account's deterministically-ranked
playbook candidates, produce (a) a one-line manager's read and (b) the top <=3
actions, selecting `play_id` only from a schema enum so the model cannot invent
an off-playbook action. Everything authoritative (score, factors, ranking,
collapse) is computed upstream; the LLM only selects + phrases.

Provider is swappable behind LLMProvider. Default: OpenRouter -> Gemini
Flash-Lite (model id in config). Key is read from the OPENROUTER_API_KEY env
var — never stored in the repo.

Failure policy (per product decision): if a provider is configured but its
output fails validation, return None so the caller HIDES the section (the
deterministic "Why this score" panel always remains). If no provider is
configured at all, fall back to rendering the deterministic candidates so the
feature is still demoable without a key.
"""
from __future__ import annotations

import json
import os
import re
from typing import Protocol

from . import config as C
from . import insights
from .playbook import PLAY_IDS

_PROMPT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "prompts", "top3_actions.system.md")


def _system_prompt() -> str:
    with open(_PROMPT_PATH, encoding="utf-8") as f:
        text = f.read()
    text = text.split("<!-- CACHE_SPLIT")[0]          # static, cacheable half
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)  # strip HTML comments
    return text.strip()


def _response_schema() -> dict:
    """JSON schema for structured output; play_id enum enforces playbook-only."""
    return {
        "name": "account_actions", "strict": True,
        "schema": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "actions": {
                    "type": "array", "maxItems": C.MAX_ACTIONS,
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "properties": {
                            "play_id": {"type": "string", "enum": PLAY_IDS},
                            "headline": {"type": "string"},
                            "addresses": {"type": "array", "items": {"type": "string"}},
                            "why_now": {"type": "string"},
                            "horizon": {"type": "string", "enum": ["quick", "weeks"]},
                        },
                        "required": ["play_id", "headline", "addresses", "why_now", "horizon"],
                    },
                },
            },
            "required": ["summary", "actions"],
        },
    }


def _user_message(account: dict, band: str, score: int, changed: dict,
                  candidates: list[dict]) -> str:
    """Data first, closing instruction last (Gemini long-context guidance)."""
    was = f" (was {score - changed['score_delta']}, {changed.get('direction', 'flat')})" if changed.get("score_delta") else ""
    months = insights.months_to_renewal(account.get("renewal_date", ""))
    lines = [
        "<account_data>",
        f"Account: {account['name']} — {band.upper()} {score}/100{was}, renewal in ~{max(months, 0)} months.",
        "Candidates (priority-ranked):",
    ]
    for i, c in enumerate(candidates, 1):
        lines.append(f"{i}. {c['play_id']} [addresses: {'; '.join(c['addresses'])}]")
    lines += [
        "</account_data>", "",
        "Based on the account data above, produce the manager's summary and the "
        "top actions per the rules. Return only the JSON.",
    ]
    return "\n".join(lines)


# ---------------- provider seam ----------------
class LLMProvider(Protocol):
    def complete(self, system: str, user: str, schema: dict) -> str: ...


class OpenRouterProvider:
    """OpenRouter (OpenAI-compatible). Structured output via response_format."""
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    def complete(self, system: str, user: str, schema: dict) -> str:
        import requests  # local import so the app runs without the dep until used
        r = requests.post(
            self.URL,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "temperature": C.LLM_TEMPERATURE,
                "max_tokens": C.LLM_MAX_TOKENS,
                "response_format": {"type": "json_schema", "json_schema": schema},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def _provider() -> LLMProvider | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    return OpenRouterProvider(key, C.LLM_MODEL) if key else None


def _validate(parsed: dict, candidates: list[dict]) -> bool:
    """Semantic checks structured output can't guarantee."""
    cand_ids = {c["play_id"] for c in candidates}
    valid_signals = {s for c in candidates for s in c["addresses"]}
    actions = parsed.get("actions")
    if not isinstance(parsed.get("summary"), str) or not isinstance(actions, list):
        return False
    if len(actions) > C.MAX_ACTIONS:
        return False
    for a in actions:
        if a.get("play_id") not in cand_ids:                 # off-candidate play
            return False
        if any(sig not in valid_signals for sig in a.get("addresses", [])):
            return False                                     # invented / uncited signal
    return True


def recommend_actions(account: dict, band: str, score: int, factors: list[dict]) -> dict | None:
    """Orchestrate: deterministic candidates -> LLM select+phrase -> validate.

    Returns {source, summary, actions, what_changed} or None (caller hides).
    """
    changed = insights.what_changed(account["id"])
    candidates = insights.rank_candidates(factors, account, band)

    class_by_id = {c["play_id"]: c["class"] for c in candidates}

    provider = _provider()
    if provider is None:
        # No key: render the deterministic candidates so the feature is demoable.
        return {
            "source": "deterministic", "what_changed": changed,
            "summary": None,
            "actions": [{"play_id": c["play_id"], "class": c["class"], "headline": c["title"],
                         "addresses": c["addresses"], "why_now": "", "horizon": "weeks"}
                        for c in candidates],
        }
    try:
        raw = provider.complete(_system_prompt(),
                                _user_message(account, band, score, changed, candidates),
                                _response_schema())
        parsed = json.loads(raw)
        if not _validate(parsed, candidates):
            return None                                      # hide the section
        for a in parsed["actions"]:
            a["class"] = class_by_id.get(a["play_id"], "operational")
        return {"source": "llm", "what_changed": changed,
                "summary": parsed["summary"], "actions": parsed["actions"]}
    except Exception:
        return None                                          # hide on any failure
