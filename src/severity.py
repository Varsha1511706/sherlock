# src/severity.py
"""SLO burn, severity, MTTR, and error budget — driven by data/slos.json."""
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd


def load_slos(path: str = "data/slos.json") -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def slo_burn(logs_df: pd.DataFrame, incident: dict, slos: dict) -> dict:
    if logs_df is None or logs_df.empty:
        return {}
    start = pd.to_datetime(incident["start"], utc=True)
    end = pd.to_datetime(incident["end"], utc=True)
    window = logs_df[(logs_df["minute"] >= start) & (logs_df["minute"] <= end)]

    out = {}
    for svc in incident.get("affected_services", []):
        svc_logs = window[window["service"] == svc]
        if svc_logs.empty:
            continue
        total = len(svc_logs)
        errors = int(svc_logs["is_error"].sum())
        err_rate = errors / total if total else 0
        cfg = slos.get(svc, {})
        slo = cfg.get("slo", 0.99)
        allowed = max(1 - slo, 1e-6)
        out[svc] = {
            "error_rate": round(err_rate, 4),
            "slo_target": slo,
            "burn_rate": round(err_rate / allowed, 2),
            "criticality": cfg.get("criticality", 1.0),
        }
    return out


def error_budget(logs_df, slos: dict, window_days: int = 30) -> pd.DataFrame:
    """Cumulative error budget consumption per service."""
    if logs_df is None or logs_df.empty:
        return pd.DataFrame()
    rows = []
    for svc, grp in logs_df.groupby("service"):
        cfg = slos.get(svc, {})
        slo = cfg.get("slo", 0.99)
        allowed = 1 - slo  # fraction allowed to fail
        total = len(grp)
        errors = int(grp["is_error"].sum())
        consumed = errors / total if total else 0
        rows.append({
            "service": svc,
            "slo": slo,
            "error_rate": round(consumed, 4),
            "budget_total": round(allowed, 4),
            "budget_consumed": round(consumed, 4),
            "budget_remaining_pct": round(max(0, 1 - consumed / allowed) * 100, 1),
        })
    return pd.DataFrame(rows)


def severity_class(burn: dict, incident: dict) -> dict:
    n = len(incident.get("affected_services", []))
    origin = incident.get("probable_origin", "")
    max_burn = max((v["burn_rate"] for v in burn.values()), default=0)
    crit = max((v["criticality"] for v in burn.values()), default=1.0)

    score = max_burn * crit * (1 + 0.15 * (n - 1))

    if score >= 40:  sev, color, label = "SEV-1", "#dc2626", "Critical"
    elif score >= 15: sev, color, label = "SEV-2", "#f59e0b", "High"
    elif score >= 5: sev, color, label = "SEV-3", "#eab308", "Medium"
    else: sev, color, label = "SEV-4", "#22c55e", "Low"

    return {"sev": sev, "color": color, "label": label,
            "score": round(score, 2), "max_burn": round(max_burn, 2),
            "n_services": n}


def estimate_mttr(anomalies, incident) -> dict:
    if anomalies is None or anomalies.empty:
        return {}
    start = pd.to_datetime(incident["start"], utc=True)
    end = pd.to_datetime(incident["end"], utc=True)
    w = anomalies[(anomalies["minute"] >= start) & (anomalies["minute"] <= end)]
    if w.empty:
        return {}

    first, last = w["minute"].min(), w["minute"].max()
    spread = max((last - first).total_seconds() / 60, 1)
    svc_first = w.groupby("service")["minute"].min().sort_values()
    mttd = ((svc_first.iloc[1] - svc_first.iloc[0]).total_seconds() / 60
            if len(svc_first) >= 2 else 1.0)
    cascade_depth = len(incident.get("affected_services", []))
    mttr = spread + 2 * cascade_depth

    # Confidence band ±20%
    return {
        "mttd_min": round(mttd, 1),
        "mttr_min": round(mttr, 1),
        "mttr_low": round(mttr * 0.8, 1),
        "mttr_high": round(mttr * 1.2, 1),
        "spread_min": round(spread, 1),
        "cascade_depth": cascade_depth,
    }


def business_impact(severity, mttr, incident) -> dict:
    n = severity["n_services"]
    mttr_min = mttr.get("mttr_min", 5)
    sev_w = {"SEV-1": 10, "SEV-2": 5, "SEV-3": 2, "SEV-4": 1}[severity["sev"]]
    score = n * mttr_min * sev_w / 10
    return {
        "impact_score": round(score, 1),
        "estimated_users_affected": n * 1000,
        "downtime_min": round(mttr_min, 1),
    }


def full_report(logs_df, anomalies, incident, slos=None) -> dict:
    slos = slos or load_slos()
    burn = slo_burn(logs_df, incident, slos)
    sev = severity_class(burn, incident)
    mttr = estimate_mttr(anomalies, incident)
    impact = business_impact(sev, mttr, incident)
    return {"burn": burn, "severity": sev, "mttr": mttr, "impact": impact}
