"""
Realistic synthetic log generator for the RCA Engine.
Produces ~4500 log lines across 60 minutes with structured fields,
trace IDs, and three injected incidents.
"""
import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

random.seed(1337)

SERVICES = {
    "api-gateway":     {"weight": 0.35, "criticality": "high"},
    "auth-service":    {"weight": 0.25, "criticality": "critical"},
    "payment-service": {"weight": 0.20, "criticality": "critical"},
    "db-service":      {"weight": 0.20, "criticality": "critical"},
}

NORMAL_MSGS = {
    "api-gateway": [
        ("GET /api/v1/users 200", 200),
        ("POST /api/v1/orders 201", 201),
        ("GET /api/v1/products 200", 200),
        ("GET /health 200", 200),
        ("PUT /api/v1/profile 200", 200),
        ("DELETE /api/v1/cart 204", 204),
    ],
    "auth-service": [
        ("token validated", 200),
        ("user session refreshed", 200),
        ("login success", 200),
        ("MFA challenge issued", 200),
        ("token refresh completed", 200),
    ],
    "payment-service": [
        ("charge processed", 200),
        ("refund queued", 200),
        ("webhook received from stripe", 200),
        ("payment intent created", 200),
        ("subscription renewed", 200),
    ],
    "db-service": [
        ("query executed in 8ms", 200),
        ("query executed in 12ms", 200),
        ("connection acquired", 200),
        ("index hit on orders_user_id", 200),
        ("transaction committed", 200),
        ("vacuum completed", 200),
    ],
}

# Three incident windows with distinct root causes
INCIDENTS = [
    {
        "start_min": 15, "duration": 5,
        "origin": "db-service",
        "origin_msg": ("FATAL: connection pool exhausted (100/100)", 503),
        "cascade": [
            ("auth-service",    "500 upstream db timeout", 500, 3),
            ("api-gateway",     "500 from auth-service", 500, 6),
            ("payment-service", "502 from upstream", 502, 8),
        ],
    },
    {
        "start_min": 38, "duration": 4,
        "origin": "auth-service",
        "origin_msg": ("JWT validation failed: clock skew 12s", 401),
        "cascade": [
            ("api-gateway",     "401 unauthorized from auth-service", 401, 2),
            ("payment-service", "auth check failed for charge", 401, 5),
        ],
    },
    {
        "start_min": 52, "duration": 6,
        "origin": "payment-service",
        "origin_msg": ("upstream timeout after 5000ms", 504),
        "cascade": [
            ("api-gateway", "504 gateway timeout from payment-service", 504, 4),
        ],
    },
]


def _trace_id() -> str:
    return uuid.uuid4().hex[:16]


def _make_ts(base: datetime, sec_offset: int) -> str:
    return (base + timedelta(seconds=sec_offset)).isoformat()


def generate(total_minutes: int = 60, out_path: str = "data/logs.json") -> int:
    start = datetime.utcnow().replace(microsecond=0) - timedelta(minutes=total_minutes)
    logs = []

    # baseline traffic
    for minute in range(total_minutes):
        base = start + timedelta(minutes=minute)
        # ~70 events per minute across services
        for _ in range(70):
            svc = random.choices(
                list(SERVICES.keys()),
                weights=[s["weight"] for s in SERVICES.values()],
                k=1,
            )[0]
            msg, code = random.choice(NORMAL_MSGS[svc])
            logs.append({
                "timestamp": _make_ts(base, random.randint(0, 59)),
                "service": svc,
                "level": "INFO",
                "message": msg,
                "trace_id": _trace_id(),
                "status_code": code,
                "duration_ms": random.randint(4, 180),
            })

        # sprinkle a few WARNs for realism
        if random.random() < 0.3:
            svc = random.choice(list(SERVICES.keys()))
            logs.append({
                "timestamp": _make_ts(base, random.randint(0, 59)),
                "service": svc,
                "level": "WARN",
                "message": "high memory usage (82%)" if svc == "api-gateway" else "slow query (>200ms)",
                "trace_id": _trace_id(),
                "status_code": 200,
                "duration_ms": random.randint(200, 800),
            })

    # inject incidents
    for inc in INCIDENTS:
        for minute_offset in range(inc["duration"]):
            base = start + timedelta(minutes=inc["start_min"] + minute_offset)

            # origin errors
            for _ in range(30):
                msg, code = inc["origin_msg"]
                logs.append({
                    "timestamp": _make_ts(base, random.randint(0, 59)),
                    "service": inc["origin"],
                    "level": "ERROR",
                    "message": msg,
                    "trace_id": _trace_id(),
                    "status_code": code,
                    "duration_ms": random.randint(3000, 8000),
                })

            # cascade errors
            for cascade_svc, cascade_msg, code, delay in inc["cascade"]:
                for _ in range(15):
                    logs.append({
                        "timestamp": _make_ts(base, random.randint(delay, 59)),
                        "service": cascade_svc,
                        "level": "ERROR",
                        "message": cascade_msg,
                        "trace_id": _trace_id(),
                        "status_code": code,
                        "duration_ms": random.randint(1000, 6000),
                    })

    logs.sort(key=lambda x: x["timestamp"])

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(logs, indent=2), encoding="utf-8")
    return len(logs)


if __name__ == "__main__":
    n = generate()
    print(f"Wrote {n} log lines to data/logs.json")
