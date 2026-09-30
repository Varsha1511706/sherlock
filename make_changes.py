import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

# anchor changes to match the log file's start time
logs = json.loads(Path("data/logs.json").read_text(encoding="utf-8-sig"))
start = datetime.fromisoformat(logs[0]["timestamp"]).replace(tzinfo=timezone.utc)
# put a deploy ~1 minute before each incident window
offsets_min = [14, 37, 51]

changes = [
    {"id": "DEP-101", "timestamp": (start + timedelta(minutes=offsets_min[0])).isoformat(),
     "service": "db-service",      "kind": "config", "version": "pool-size-200", "author": "alice"},
    {"id": "DEP-102", "timestamp": (start + timedelta(minutes=offsets_min[1])).isoformat(),
     "service": "auth-service",    "kind": "deploy", "version": "v3.2.0",        "author": "bob"},
    {"id": "DEP-103", "timestamp": (start + timedelta(minutes=offsets_min[2])).isoformat(),
     "service": "payment-service", "kind": "deploy", "version": "v1.9.0",        "author": "carol"},
]

Path("data/changes.json").write_text(
    json.dumps({"changes": changes}, indent=2), encoding="utf-8")
print(f"Wrote {len(changes)} changes anchored to log start {start.isoformat()}")
