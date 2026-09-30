# src/fault_injector.py
"""
Fault injection testbed: generates synthetic logs across 4 services
with a labeled fault type for evaluation.

Each fault has a known ground-truth root cause. This is what lets us
measure accuracy of the RCA pipeline.
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

SERVICES = ["api-gateway", "auth-service", "payment-service", "db-service"]

NORMAL_MSGS = {
    "api-gateway": ["GET /api/v1/users 200", "POST /api/v1/orders 201", "GET /health 200"],
    "auth-service": ["token validated", "user session refreshed", "login success"],
    "payment-service": ["charge processed", "refund queued", "webhook received"],
    "db-service": ["query executed in 12ms", "connection acquired", "index hit"],
}

# Each fault: which service starts it, cascades to, error messages, ground truth
FAULTS = {
    "db_connection_pool": {
        "origin": "db-service",
        "cascades": ["auth-service", "api-gateway"],
        "origin_msg": "FATAL: connection pool exhausted (100/100)",
        "cascade_msg": "500 upstream db timeout",
        "ground_truth": "connection_pool_saturation",
    },
    "memory_leak": {
        "origin": "api-gateway",
        "cascades": ["payment-service"],
        "origin_msg": "OOM: heap usage 98%, GC pause 4.2s",
        "cascade_msg": "503 upstream api-gateway timeout",
        "ground_truth": "memory_leak",
    },
    "network_latency": {
        "origin": "payment-service",
        "cascades": ["api-gateway"],
        "origin_msg": "upstream timeout after 5000ms",
        "cascade_msg": "504 gateway timeout from payment-service",
        "ground_truth": "network_latency",
    },
    "auth_cascade": {
        "origin": "auth-service",
        "cascades": ["api-gateway", "payment-service"],
        "origin_msg": "JWT validation failed: clock skew 12s",
        "cascade_msg": "401 unauthorized from auth-service",
        "ground_truth": "auth_single_point_of_failure",
    },
    "third_party_outage": {
        "origin": "payment-service",
        "cascades": ["api-gateway"],
        "origin_msg": "stripe API returned 503 after 3 retries",
        "cascade_msg": "502 bad gateway from payment-service",
        "ground_truth": "third_party_outage",
    },
    "bad_deploy": {
        "origin": "api-gateway",
        "cascades": ["auth-service"],
        "origin_msg": "panic: nil pointer dereference in handler",
        "cascade_msg": "500 internal error from api-gateway",
        "ground_truth": "bad_deploy_upstream_unavailable",
    },
}


def generate_with_fault(fault_type: str, total_minutes: int = 60,
                        fault_start: int = 30, fault_duration: int = 8,
                        seed: int | None = None) -> dict:
    """
    Generate logs with a specific injected fault.

    Returns:
        {
          "logs": [...],
          "ground_truth": {
            "root_cause": "...",
            "origin_service": "...",
            "affected_services": [...],
            "fault_type": "...",
          }
        }
    """
    if fault_type not in FAULTS:
        raise ValueError(f"Unknown fault: {fault_type}. "
                         f"Options: {list(FAULTS.keys())}")

    if seed is not None:
        random.seed(seed)
    else:
        random.seed()

    fault = FAULTS[fault_type]
    start = datetime.utcnow() - timedelta(minutes=total_minutes)
    logs = []

    for minute in range(total_minutes):
        ts_base = start + timedelta(minutes=minute)
        in_fault = fault_start <= minute < fault_start + fault_duration

        # Normal traffic for all services
        for svc in SERVICES:
            for _ in range(random.randint(8, 15)):
                logs.append({
                    "timestamp": (ts_base + timedelta(seconds=random.randint(0, 59))).isoformat(),
                    "service": svc,
                    "level": "INFO",
                    "message": random.choice(NORMAL_MSGS[svc]),
                })

        if in_fault:
            # Origin service errors first (burst)
            for _ in range(random.randint(18, 25)):
                logs.append({
                    "timestamp": (ts_base + timedelta(seconds=random.randint(0, 60))).isoformat(),
                    "service": fault["origin"],
                    "level": "ERROR",
                    "message": fault["origin_msg"],
                })
            # Cascades follow a few seconds later
            for svc in fault["cascades"]:
                for _ in range(random.randint(10, 16)):
                    logs.append({
                        "timestamp": (ts_base + timedelta(seconds=random.randint(3, 60))).isoformat(),
                        "service": svc,
                        "level": "ERROR",
                        "message": fault["cascade_msg"],
                    })

    logs.sort(key=lambda x: x["timestamp"])

    return {
        "logs": logs,
        "ground_truth": {
            "root_cause": fault["ground_truth"],
            "origin_service": fault["origin"],
            "affected_services": [fault["origin"]] + fault["cascades"],
            "fault_type": fault_type,
        },
    }


def generate_all_faults(out_dir: str = "data/testbed") -> dict:
    """Generate a labeled test set: one run per fault type."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    manifest = {}
    for fault_type in FAULTS:
        result = generate_with_fault(fault_type, seed=hash(fault_type) % 10_000)
        file = out_path / f"{fault_type}.json"
        file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        manifest[fault_type] = {
            "path": str(file),
            "ground_truth": result["ground_truth"],
            "n_logs": len(result["logs"]),
        }

    (out_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print("Generating testbed...")
    m = generate_all_faults()
    for k, v in m.items():
        print(f"  ✓ {k:22s} → {v['n_logs']} logs → root_cause={v['ground_truth']['root_cause']}")
    print(f"\nWrote {len(m)} labeled scenarios to data/testbed/")