# src/detect.py
"""
Anomaly detection via EWMA control chart + Poisson change-point.

Why EWMA over z-score:
  - Error rates are Poisson-ish, heavy-tailed, and seasonal.
  - EWMA adapts to drift and detects gradual degradations.
  - Control limits from the smoothed series, not the raw one.
"""
import numpy as np
import pandas as pd


EMPTY_COLUMNS = ["service", "minute", "error_rate", "ewma", "ucl", "lcl",
                 "zscore", "errors", "total", "score"]


def _ewma_series(values, alpha=0.3):
    out = np.zeros_like(values, dtype=float)
    if len(values) == 0:
        return out
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _poisson_changepoint(counts):
    """
    Simple CUSUM-style change-point test.
    Returns True if a shift is detected.
    """
    if len(counts) < 6:
        return False
    first, second = counts[:len(counts) // 2], counts[len(counts) // 2:]
    mu1, mu2 = first.mean(), second.mean()
    sd = max(counts.std(), 1e-6)
    return abs(mu2 - mu1) / sd > 1.5 and mu2 > mu1


def detect_anomalies(logs: list, alpha: float = 0.3,
                     k_sigma: float = 3.0,
                     z_threshold: float = 3.0) -> pd.DataFrame:
    """Detect error-rate anomalies per service using EWMA + control limits."""
    if not logs:
        return pd.DataFrame(columns=EMPTY_COLUMNS)

    df = pd.DataFrame(logs)
    if df.empty:
        return pd.DataFrame(columns=EMPTY_COLUMNS)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return pd.DataFrame(columns=EMPTY_COLUMNS)

    df["is_error"] = df["level"].isin(["ERROR", "FATAL"]).astype(int)
    df["minute"] = df["timestamp"].dt.floor("1min")

    agg = df.groupby(["service", "minute"]).agg(
        total=("is_error", "size"),
        errors=("is_error", "sum"),
    ).reset_index()
    agg["error_rate"] = agg["errors"] / agg["total"]

    results = []
    for svc, grp in agg.groupby("service"):
        grp = grp.sort_values("minute").reset_index(drop=True)
        rates = grp["error_rate"].values
        counts = grp["errors"].values

        ewma = _ewma_series(rates, alpha=alpha)
        # residual std from the raw minus smoothed
        resid = rates - ewma
        sd = np.std(resid) if np.std(resid) > 0 else 1e-6

        ucl = ewma + k_sigma * sd
        lcl = ewma - k_sigma * sd

        # zscore against smoothed baseline
        z = (rates - ewma) / sd

        # change-point flag on raw counts
        cp = _poisson_changepoint(counts)

        for i, row in grp.iterrows():
            is_anomaly = (rates[i] > ucl[i] and z[i] > z_threshold)
            if cp and i >= len(grp) // 2:
                is_anomaly = is_anomaly or (rates[i] > ewma[i] * 2)
            if is_anomaly:
                results.append({
                    "service": svc,
                    "minute": row["minute"],
                    "error_rate": round(float(rates[i]), 4),
                    "ewma": round(float(ewma[i]), 4),
                    "ucl": round(float(ucl[i]), 4),
                    "lcl": round(float(lcl[i]), 4),
                    "zscore": round(float(z[i]), 2),
                    "errors": int(counts[i]),
                    "total": int(row["total"]),
                    "score": round(float(z[i] * np.log1p(counts[i])), 2),
                })

    if not results:
        return pd.DataFrame(columns=EMPTY_COLUMNS)

    out = pd.DataFrame(results)[EMPTY_COLUMNS]
    return out.sort_values("minute").reset_index(drop=True)
