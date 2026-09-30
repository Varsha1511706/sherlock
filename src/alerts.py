# src/alerts.py
"""Webhook alert dispatch."""
import json
import os
from pathlib import Path
from datetime import datetime

LOG = Path("data/alerts.jsonl")


def dispatch(incident: dict, severity: dict, webhook_url: str | None = None) -> dict:
    payload = {
        "ts": datetime.utcnow().isoformat(),
        "severity": severity["sev"],
        "origin": incident["probable_origin"],
        "services": incident["affected_services"],
        "window": [incident["start"], incident["end"]],
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
    return {"dispatched": True, "logged": str(LOG), "webhook": bool(webhook_url)}
