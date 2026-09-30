# src/changes.py
"""Correlate incidents with change events (deploys/config)."""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta


def load_changes(path: str = "data/changes.json") -> list:
    p = Path(path)
    if not p.exists(): return []
    return json.loads(p.read_text(encoding="utf-8")).get("changes", [])


def correlate(incident: dict, changes: list, window_min: int = 15) -> list:
    start = datetime.fromisoformat(incident["start"]).replace(tzinfo=timezone.utc)
    hits = []
    for c in changes:
        try:
            ts = datetime.fromisoformat(c["timestamp"]).replace(tzinfo=timezone.utc)
        except Exception:
            continue
        delta_min = (start - ts).total_seconds() / 60
        if -2 <= delta_min <= window_min:
            hits.append({**c, "delta_min_before_incident": round(delta_min, 1)})
    return hits
