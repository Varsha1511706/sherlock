# src/seed_incidents.py
import json
from pathlib import Path

INCIDENTS = [
    {"id": "INC-001", "summary": "DB connection pool exhausted due to slow queries",
     "root_cause": "connection_pool_saturation", "services": ["db-service", "auth-service"],
     "resolution": "increase pool size to 200, add query timeout of 5s"},
    {"id": "INC-002", "summary": "Auth service 500s after DB restart",
     "root_cause": "stale_connections_after_db_restart", "services": ["auth-service", "db-service"],
     "resolution": "restart auth pods, enable connection health check"},
    {"id": "INC-003", "summary": "Payment service timeouts under load",
     "root_cause": "thread_pool_exhaustion", "services": ["payment-service"],
     "resolution": "increase worker threads, add circuit breaker"},
    {"id": "INC-004", "summary": "API gateway 502s during deploy",
     "root_cause": "bad_deploy_upstream_unavailable", "services": ["api-gateway"],
     "resolution": "rollback deploy, add readiness probe"},
    {"id": "INC-005", "summary": "DB replication lag causing stale reads",
     "root_cause": "replication_lag", "services": ["db-service"],
     "resolution": "route reads to primary, investigate replica IO"},
    {"id": "INC-006", "summary": "Auth token validation failures spike",
     "root_cause": "clock_skew_jwt_invalid", "services": ["auth-service"],
     "resolution": "sync NTP, extend JWT leeway"},
    {"id": "INC-007", "summary": "Payment gateway upstream 503s",
     "root_cause": "third_party_outage", "services": ["payment-service"],
     "resolution": "enable retry with backoff, notify vendor"},
    {"id": "INC-008", "summary": "Memory leak in API gateway causes OOM",
     "root_cause": "memory_leak", "services": ["api-gateway"],
     "resolution": "restart pods, profile heap, patch leak"},
    {"id": "INC-009", "summary": "DB CPU saturation from missing index",
     "root_cause": "missing_index", "services": ["db-service"],
     "resolution": "add composite index on orders(user_id, created_at)"},
    {"id": "INC-010", "summary": "Cascading failures from auth to all services",
     "root_cause": "auth_single_point_of_failure", "services": ["auth-service", "api-gateway", "payment-service"],
     "resolution": "add auth caching, circuit breaker, fallback auth"},
    {"id": "INC-011", "summary": "Connection pool exhaustion after traffic spike",
     "root_cause": "connection_pool_saturation", "services": ["db-service", "payment-service"],
     "resolution": "autoscale pool, add connection queue metrics"},
    {"id": "INC-012", "summary": "Slow queries from N+1 ORM pattern",
     "root_cause": "n_plus_one_queries", "services": ["db-service", "payment-service"],
     "resolution": "batch fetch, add eager loading"},
]

Path("data").mkdir(exist_ok=True)
out_path = Path("data/incidents.json")
out_path.write_text(json.dumps(INCIDENTS, indent=2), encoding="utf-8")
print(f"Wrote {len(INCIDENTS)} historical incidents to {out_path}")
print(f"File size: {out_path.stat().st_size} bytes")