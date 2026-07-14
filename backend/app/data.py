"""CSV data layer.

Per the project decision, every "table" is a CSV file on disk. This module is
the only place that touches the filesystem, so the rest of the app treats the
CSVs as if they were tables: read returns a list of dict rows, write replaces
or appends. Swap this module for a real DB later and nothing above it changes.

Tables:
  accounts.csv      one row per account (input facts)
  module_usage.csv  account_id, module, nsm_attainment_pct   (input)
  metrics.csv       account_id, nps, csat, support_state, champion_status,
                    billing_state                            (input)
  signals.csv       the unified timeline / scoring inputs     (input)
  health_score.csv  computed, immutable snapshots (append-only)
  score_factor.csv  computed factor breakdown per snapshot
"""
from __future__ import annotations

import csv
import os
from typing import Iterable

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

TABLES = {
    "accounts": "accounts.csv",
    "module_usage": "module_usage.csv",
    "metrics": "metrics.csv",
    "signals": "signals.csv",
    "health_score": "health_score.csv",
    "score_factor": "score_factor.csv",
}


def _path(table: str) -> str:
    if table not in TABLES:
        raise KeyError(f"unknown table {table!r}")
    return os.path.join(DATA_DIR, TABLES[table])


def read(table: str) -> list[dict]:
    """Return all rows of a table as a list of dicts (empty if file missing)."""
    path = _path(table)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(table: str, rows: Iterable[dict], fieldnames: list[str]) -> None:
    """Replace a table with the given rows."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = _path(table)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def append(table: str, rows: Iterable[dict], fieldnames: list[str]) -> None:
    """Append rows (immutable snapshots write here)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = _path(table)
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)
