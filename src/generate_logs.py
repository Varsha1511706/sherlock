# src/generate_logs.py
"""
Synthetic log generator + fault injection utilities.

Exposes:
    generate()             — baseline logs (no fault)
    inject_fault(...)      — inject a named fault (used by fault_injector)
    save_logs(logs, path)  — write logs to JSON
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

SERVICES = ["api-gateway", "auth-service", "payment-service", "db-service"]

NORMAL_MSGS = {
    "api-gateway": ["GET /api/v1/users 200", "POST /api/v1/orders 201"],
    "auth-service": ["token validated", "user session refreshed"],
    "payment-service": ["charge processed", "refund queued"],
    "db-service": ["query executed in 12ms", "connection acquired"],
}

INCIDENT_START = 30
INCIDENT_DURATION = 8


def _emit(logs, ts, service, level, message):
    logs.append({
        "timestamp": ts.isoformat(),
        "service": service,
        "level": level,
        "message": message,
    })


def generate(total_minutes: int = 60, seed: int = 42,
             out_path: str = "data/logs.json") -> list:
    """Baseline synthetic logs with a single injected DB saturation incident."""
    random.seed(seed)
    start = datetime.utcnow() - timedelta(minutes=total_minutes)
    logs = []

    for minute in range(total_minutes):
        ts_base = start + timedelta(minutes=minute)
        in_incident = INCIDENT_START <= minute < INCIDENT_START + INCIDENT_DURATION

        for svc in SERVICES:
            for _ in range(random.randint(8, 15)):
                _emit(logs, ts_base + timedelta(seconds=random.randint(0, 59)),
                      svc, "INFO", random.choice(NORMAL_MSGS[svc]))

        if in_incident:
            for _ in range(20):
                _emit(logs, ts_base + timedelta(seconds=random.randint(0, 60)),
                      "db-service", "ERROR",
                      "FATAL: connection pool exhausted (100/100)")
            for _ in range(15):
                _emit(logs, ts_base + timedelta(seconds=random.randint(2, 60)),
                      "auth-service", "ERROR", "500 upstream db timeout")
            for _ in range(10):
                _emit(logs, ts_base + timedelta(seconds=random.randint(4, 60)),
                      "api-gateway", "ERROR", "500 from auth-service")

    logs.sort(key=lambda x: x["timestamp"])
    save_logs(logs, out_path)
    print(f"Wrote {len(logs)} log lines to {out_path}")
    return logs


def inject_fault(fault_type: str, total_minutes: int = 60,
                 fault_start: int = 30, fault_duration: int = 8,
                 seed: int | None = None) -> list:
    """
    Generate logs with a specific fault injected.
    Thin wrapper — actual fault catalog lives in `fault_injector.FAULTS`.

    Kept here so `generate_logs` remains importable without fault_injector,
    and so tests can call inject_fault directly.
    """
    from src.fault_injector import generate_with_fault
    result = generate_with_fault(
        fault_type,
        total_minutes=total_minutes,
        fault_start=fault_start,
        fault_duration=fault_duration,
        seed=seed,
    )
    return result["logs"]


def save_logs(logs: list, path: str = "data/logs.json") -> None:
    """Write a log list to JSON, creating parent dirs."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(logs, indent=2), encoding="utf-8")


if __name__ == "__main__":
    generate()