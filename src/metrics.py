# src/metrics.py
"""Stub metrics ingestion — placeholder for Prometheus/CloudWatch integration."""
import json
from pathlib import Path


def load_metrics(path: str = "data/metrics.json") -> dict:
    p = Path(path)
    if not p.exists(): return {}
    return json.loads(p.read_text(encoding="utf-8"))


def correlate(incident: dict, metrics: dict) -> list:
    """Placeholder correlation. Real impl fetches per-service metrics."""
    return []
