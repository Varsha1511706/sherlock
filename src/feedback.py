# src/feedback.py
"""Persisted feedback + retrieval re-rank."""
import json
from pathlib import Path
from datetime import datetime

LEDGER = Path("data/feedback.jsonl")


def record(incident_id: str, root_cause: str, correct: bool) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": datetime.utcnow().isoformat(),
            "incident_id": incident_id,
            "root_cause": root_cause,
            "correct": correct,
        }) + "\n")


def get_rerank_boost(root_cause: str) -> float:
    """Simple re-rank: correct predictions get +10% weight."""
    if not LEDGER.exists():
        return 1.0
    correct = total = 0
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("root_cause") == root_cause:
            total += 1
            correct += int(r.get("correct", False))
    if total == 0:
        return 1.0
    return 1.0 + (correct / total - 0.5) * 0.2
