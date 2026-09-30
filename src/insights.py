# src/insights.py
"""
Pattern mining and forecasting on top of incidents.

Provides:
  - Recurring pattern detection across incidents
  - Next-likely-incident forecast from service temporal patterns
  - SLO burn projection for the next N minutes
  - Prevention recommendations
"""
import pandas as pd
from datetime import timedelta


def recurring_patterns(incidents: list) -> list:
    """
    Find root causes that appear in >1 incident or overlapping services.
    Returns list of {root_cause, count, incidents, recommendation}.
    """
    by_cause = {}
    for r in incidents:
        rc = r["report"].get("root_cause", "unknown")
        by_cause.setdefault(rc, []).append(r["incident"])

    out = []
    for rc, incs in by_cause.items():
        if len(incs) >= 1:  # even a single occurrence gets a prevention tip
            services = set()
            for i in incs:
                services.update(i.get("affected_services", []))
            out.append({
                "root_cause": rc,
                "count": len(incs),
                "services": sorted(services),
                "recommendation": _prevention_for(rc),
            })
    return sorted(out, key=lambda x: -x["count"])


def _prevention_for(root_cause: str) -> str:
    table = {
        "connection_pool_saturation":
            "Enable connection pool autoscaling + add 80% utilization alert.",
        "memory_leak":
            "Add RSS trend alerts; enable periodic pod restarts as a stopgap.",
        "network_latency":
            "Add per-hop latency SLO; enforce circuit breaker on upstream calls.",
        "third_party_outage":
            "Add vendor status webhook + queue-based retry with DLQ.",
        "auth_single_point_of_failure":
            "Deploy auth read replica + cache tokens at edge for 5 min.",
        "bad_deploy_upstream_unavailable":
            "Enforce canary deploys with automated rollback on error rate > 3%.",
        "missing_index":
            "Enable pg_stat_statements alerts for seq scans on >100k-row tables.",
        "replication_lag":
            "Alert on replication lag > 5s; route reads to primary during lag.",
    }
    return table.get(root_cause, "Add targeted SLO alert + weekly review.")


def forecast_next_incidents(logs_df: pd.DataFrame, incidents: list,
                            horizon_min: int = 30) -> list:
    """
    Simple forecast: which services show early-warning signals (rising error rate).
    Returns list of {service, trend, current_rate, forecast_rate, eta_min}.
    """
    if logs_df is None or logs_df.empty:
        return []

    last_minute = logs_df["minute"].max()
    window_start = last_minute - timedelta(minutes=10)
    recent = logs_df[logs_df["minute"] >= window_start]

    agg = recent.groupby(["service", "minute"]).agg(
        total=("is_error", "size"),
        errors=("is_error", "sum"),
    ).reset_index()
    agg["error_rate"] = agg["errors"] / agg["total"]

    forecasts = []
    for svc, grp in agg.groupby("service"):
        if len(grp) < 3:
            continue
        grp = grp.sort_values("minute")
        # linear trend of last N minutes
        x = range(len(grp))
        y = grp["error_rate"].values
        slope = (y[-1] - y[0]) / max(len(y) - 1, 1)

        if slope > 0.02:  # rising meaningfully
            current = float(y[-1])
            # naive: rate × slope
            forecast_rate = min(current + slope * horizon_min, 1.0)
            eta = horizon_min if forecast_rate > 0.5 else None
            forecasts.append({
                "service": svc,
                "trend": "rising",
                "current_rate": round(current, 3),
                "forecast_rate": round(forecast_rate, 3),
                "slope": round(slope, 4),
                "eta_min": eta,
            })
    return sorted(forecasts, key=lambda x: -x["forecast_rate"])


def slo_burn_projection(logs_df: pd.DataFrame, horizon_min: int = 60) -> pd.DataFrame:
    """
    Project cumulative SLO burn for next `horizon_min` minutes per service.
    """
    if logs_df is None or logs_df.empty:
        return pd.DataFrame()

    last_minute = logs_df["minute"].max()
    rows = []
    for svc, grp in logs_df.groupby("service"):
        recent = grp[grp["minute"] >= last_minute - timedelta(minutes=10)]
        if recent.empty:
            continue
        rate = recent["is_error"].mean()
        for t in range(0, horizon_min + 1, 5):
            rows.append({
                "service": svc,
                "minutes_ahead": t,
                "projected_error_rate": min(rate + 0.001 * t, 1.0),
            })
    return pd.DataFrame(rows)


def prevention_recommendations(incidents: list) -> list:
    """Aggregate recommendations from recurring patterns."""
    patterns = recurring_patterns(incidents)
    return [{
        "root_cause": p["root_cause"],
        "occurrences": p["count"],
        "affected_services": p["services"],
        "action": p["recommendation"],
    } for p in patterns]