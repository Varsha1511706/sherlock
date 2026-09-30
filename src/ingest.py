# src/ingest.py
"""Robust multi-format log ingestion."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dateutil import parser as dtparser


LEVELS = {"INFO", "WARN", "WARNING", "ERROR", "FATAL", "DEBUG", "TRACE"}


def _parse_ts(value):
    """Parse ISO, epoch, syslog, or 'Sep 28 14:20:05' into UTC datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except Exception:
            return None
    s = str(value).strip()
    if not s:
        return None
    # numeric epoch
    if re.fullmatch(r"\d{10,13}", s):
        return datetime.fromtimestamp(int(s) / (1000 if len(s) == 13 else 1),
                                       tz=timezone.utc)
    try:
        dt = dtparser.parse(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def normalize_log(raw: dict) -> dict | None:
    """Normalize any log row into our canonical schema."""
    ts = _parse_ts(raw.get("timestamp") or raw.get("ts") or raw.get("time")
                    or raw.get("@timestamp"))
    if ts is None:
        return None

    svc = (raw.get("service") or raw.get("service_name")
            or raw.get("app") or raw.get("container") or "unknown")
    level = (raw.get("level") or raw.get("severity")
              or raw.get("lvl") or "INFO").upper()
    if level == "WARNING":
        level = "WARN"
    if level not in LEVELS:
        level = "INFO"

    msg = (raw.get("message") or raw.get("msg")
            or raw.get("log") or "").strip()

    return {
        "timestamp": ts,
        "service": str(svc),
        "level": level,
        "message": msg,
        "trace_id": raw.get("trace_id") or raw.get("traceId"),
        "span_id":  raw.get("span_id")  or raw.get("spanId"),
        "status_code": raw.get("status_code") or raw.get("status"),
        "duration_ms": raw.get("duration_ms") or raw.get("latency_ms"),
        "raw": raw,
    }


def load_logs(uploaded=None, path: str = "data/logs.json") -> list:
    """Load, normalize, sort logs from a file-like or path."""
    if uploaded is not None:
        raw = json.load(uploaded)
    else:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))

    if isinstance(raw, dict) and "logs" in raw:
        raw = raw["logs"]

    normalized = [normalize_log(r) for r in raw]
    normalized = [n for n in normalized if n is not None]
    normalized.sort(key=lambda x: x["timestamp"])
    return normalized


def to_dataframe(logs: list) -> pd.DataFrame:
    """Convert normalized logs into a feature-rich DataFrame."""
    df = pd.DataFrame(logs)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["is_error"] = df["level"].isin(["ERROR", "FATAL"]).astype(int)
    df["minute"] = df["timestamp"].dt.floor("1min")
    return df
