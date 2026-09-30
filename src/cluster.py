# src/cluster.py
"""Adaptive incident clustering: temporal + trace-ID linkage."""
import pandas as pd
from collections import defaultdict


def group_incidents(anomalies: pd.DataFrame,
                    window_minutes: int = 3,
                    logs_df: pd.DataFrame | None = None) -> list:
    if anomalies is None or anomalies.empty:
        return []
    if "minute" not in anomalies.columns:
        return []

    anomalies = anomalies.sort_values("minute").reset_index(drop=True)

    incidents = []
    current = [anomalies.iloc[0]]

    for i in range(1, len(anomalies)):
        row = anomalies.iloc[i]
        gap_min = (row["minute"] - current[-1]["minute"]).total_seconds() / 60

        # adaptive: if same service, allow longer gap
        same_svc = row["service"] == current[-1]["service"]
        effective_window = window_minutes * (1.5 if same_svc else 1.0)

        # trace-link override: if the two minutes share a trace_id, keep together
        trace_linked = False
        if logs_df is not None and "trace_id" in logs_df.columns:
            t1 = (logs_df[logs_df["minute"] == current[-1]["minute"]]
                    .dropna(subset=["trace_id"])["trace_id"].tolist())
            t2 = (logs_df[logs_df["minute"] == row["minute"]]
                    .dropna(subset=["trace_id"])["trace_id"].tolist())
            trace_linked = bool(set(t1) & set(t2))

        if gap_min <= effective_window or trace_linked:
            current.append(row)
        else:
            incidents.append(_summarize(current))
            current = [row]
    incidents.append(_summarize(current))
    return incidents


def _summarize(rows: list) -> dict:
    df = pd.DataFrame(rows)
    ranked = (df.groupby("service")["score"].max()
                .sort_values(ascending=False).to_dict())
    first_onset = df.groupby("service")["minute"].min().to_dict()

    return {
        "start": str(df["minute"].min()),
        "end": str(df["minute"].max()),
        "affected_services": list(ranked.keys()),
        "service_scores": {k: float(v) for k, v in ranked.items()},
        "first_onset": {k: str(v) for k, v in first_onset.items()},
        "probable_origin": next(iter(ranked)),
        "signals": df.to_dict(orient="records"),
    }
