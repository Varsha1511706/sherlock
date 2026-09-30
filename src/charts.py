# src/charts.py
"""
Premium chart builders for the RCA dashboard.

All charts:
  - Work on light and dark Streamlit themes (transparent backgrounds)
  - Share a consistent color palette
  - Encode multiple signals per chart (size + color + label)
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ── Palette ───────────────────────────────────────────────────
PALETTE = {
    "primary": "#818cf8",
    "danger": "#ef4444",
    "warning": "#f59e0b",
    "success": "#22c55e",
    "info": "#0ea5e9",
    "purple": "#a855f7",
    "pink": "#ec4899",
}

SERVICE_COLORS = {
    "api-gateway": "#6366f1",
    "auth-service": "#ec4899",
    "payment-service": "#f59e0b",
    "db-service": "#0ea5e9",
}

TRANSPARENT = "rgba(0,0,0,0)"


def _base_layout(height: int = 320, **overrides) -> dict:
    layout = dict(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor=TRANSPARENT,
        paper_bgcolor=TRANSPARENT,
        font=dict(family="Inter, system-ui, sans-serif", size=12),
        hoverlabel=dict(bgcolor="rgba(20,20,30,0.9)",
                        font=dict(color="white", size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    bgcolor=TRANSPARENT),
    )
    layout.update(overrides)
    return layout


# ═══════════════════════════════════════════════════════════════
# 1. ERROR HEATMAP
# ═══════════════════════════════════════════════════════════════
def error_rate_heatmap(logs_df: pd.DataFrame, incident: dict | None = None):
    """Service × minute heatmap with annotated cells and incident overlay."""
    if logs_df is None or logs_df.empty:
        return None

    agg = logs_df.groupby(["service", "minute"]).agg(
        total=("is_error", "size"),
        errors=("is_error", "sum"),
    ).reset_index()
    agg["error_rate"] = agg["errors"] / agg["total"]
    pivot = agg.pivot(index="service", columns="minute", values="error_rate").fillna(0)
    pivot = pivot.sort_index()

    x_labels = [str(m)[11:16] for m in pivot.columns]
    y_labels = pivot.index.tolist()
    z = pivot.values

    colorscale = [
        [0.0, "rgba(129,140,248,0.05)"],
        [0.15, "rgba(129,140,248,0.20)"],
        [0.4, "#fbbf24"],
        [0.7, "#f97316"],
        [1.0, "#dc2626"],
    ]

    fig = go.Figure(data=go.Heatmap(
        z=z, x=x_labels, y=y_labels,
        colorscale=colorscale,
        colorbar=dict(title="err %", tickformat=".0%", thickness=12),
        hovertemplate="<b>%{y}</b> at %{x}<br>Error rate: %{z:.1%}<extra></extra>",
        zmin=0, zmax=1,
    ))

    if incident:
        start_str = str(pd.to_datetime(incident["start"]))[11:16]
        end_str = str(pd.to_datetime(incident["end"]))[11:16]
        if start_str in x_labels and end_str in x_labels:
            x0 = x_labels.index(start_str)
            x1 = x_labels.index(end_str)
            fig.add_shape(
                type="rect", x0=x0 - 0.5, x1=x1 + 0.5,
                y0=-0.5, y1=len(y_labels) - 0.5,
                line=dict(color=PALETTE["danger"], width=2, dash="dot"),
                fillcolor="rgba(239,68,68,0.05)", layer="below",
            )

    fig.update_layout(**_base_layout(height=280 + 30 * len(y_labels)))
    fig.update_xaxes(showgrid=False, title="")
    fig.update_yaxes(showgrid=False, title="")
    return fig


# ═══════════════════════════════════════════════════════════════
# 2. ERROR VOLUME + CUMULATIVE
# ═══════════════════════════════════════════════════════════════
def error_volume_chart(logs_df: pd.DataFrame, incident: dict | None = None):
    """Stacked bars per service + cumulative line overlay."""
    if logs_df is None or logs_df.empty:
        return None
    errs = logs_df[logs_df["is_error"] == 1]
    if errs.empty:
        return None

    grouped = errs.groupby(["minute", "service"]).size().reset_index(name="count")

    fig = px.bar(
        grouped, x="minute", y="count", color="service", barmode="stack",
        color_discrete_map=SERVICE_COLORS,
        labels={"minute": "Time", "count": "Errors", "service": "Service"},
    )

    total_by_min = errs.groupby("minute").size().reset_index(name="total")
    total_by_min["cumulative"] = total_by_min["total"].cumsum()
    fig.add_trace(go.Scatter(
        x=total_by_min["minute"], y=total_by_min["cumulative"],
        mode="lines", name="Cumulative",
        line=dict(color=PALETTE["primary"], width=2, dash="dot"),
        yaxis="y2", hovertemplate="Cumulative: %{y}<extra></extra>",
    ))

    if incident:
        fig.add_vrect(
            x0=pd.to_datetime(incident["start"]),
            x1=pd.to_datetime(incident["end"]),
            fillcolor=PALETTE["danger"], opacity=0.08, line_width=0,
            annotation_text="Incident", annotation_position="top left",
            annotation=dict(font_size=10, font_color=PALETTE["danger"]),
        )

    fig.update_layout(
        **_base_layout(height=300),
        yaxis=dict(title="Errors per minute"),
        yaxis2=dict(title="Cumulative", overlaying="y", side="right",
                    showgrid=False, tickfont=dict(color=PALETTE["primary"])),
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 3. CAUSAL GANTT
# ═══════════════════════════════════════════════════════════════
def causal_gantt(anomalies: pd.DataFrame, incident: dict | None = None):
    """Gantt with onset markers and dashed arrows showing causal order."""
    if anomalies is None or anomalies.empty:
        return None

    df = anomalies.copy()
    df["service"] = df["service"].astype(str)

    first_onset = df.groupby("service")["minute"].min().sort_values()
    order = first_onset.index.tolist()

    rows = []
    for svc in order:
        sub = df[df["service"] == svc].sort_values("minute").reset_index(drop=True)
        if sub.empty:
            continue
        start = sub.iloc[0]["minute"]
        end = start
        for _, row in sub.iterrows():
            if (row["minute"] - end).total_seconds() <= 180:
                end = row["minute"]
            else:
                rows.append({"service": svc, "start": start, "end": end,
                             "zscore": sub["zscore"].max()})
                start = row["minute"]
                end = start
        rows.append({"service": svc, "start": start, "end": end,
                     "zscore": sub["zscore"].max()})

    bars = pd.DataFrame(rows)
    if bars.empty:
        return None

    fig = px.timeline(
        bars, x_start="start", x_end="end", y="service",
        color="zscore", color_continuous_scale="OrRd",
        hover_data={"zscore": ":.1f", "start": False, "end": False},
        labels={"zscore": "z-score"},
    )
    fig.update_yaxes(
        categoryorder="array", categoryarray=order[::-1],
        title="",
    )

    for svc in order:
        t = first_onset[svc]
        fig.add_trace(go.Scatter(
            x=[t], y=[svc], mode="markers",
            marker=dict(symbol="line-ns-open", size=14,
                        color=PALETTE["danger"], line=dict(width=2)),
            name=f"{svc} onset", showlegend=False,
            hovertemplate=f"<b>{svc}</b> first anomaly<br>%{{x}}<extra></extra>",
        ))

    origin = order[0]
    for svc in order[1:]:
        fig.add_annotation(
            x=first_onset[svc], y=svc,
            ax=first_onset[origin], ay=origin,
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowsize=1.2,
            arrowwidth=1.5, arrowcolor=PALETTE["primary"],
            opacity=0.55,
        )

    fig.update_layout(
        **_base_layout(height=260 + 40 * len(order),
                       coloraxis_colorbar=dict(title="z", thickness=12)),
        xaxis_title="Time",
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 4. CASCADE FLOW
# ═══════════════════════════════════════════════════════════════
def cascade_flow(incident: dict, report: dict):
    """Horizontal cascade with node sizing by severity."""
    origin = incident["probable_origin"]
    affected = [s for s in report.get("affected_services", []) if s != origin]
    nodes = [origin] + affected

    scores = incident.get("service_scores", {})
    max_z = max(scores.values()) if scores else 1.0

    x_positions = [0] + [1 + i * 1.1 for i in range(len(affected))]
    y_positions = [0] * len(nodes)

    fig = go.Figure()
    for i in range(1, len(nodes)):
        x0, y0 = x_positions[0], y_positions[0]
        x1, y1 = x_positions[i], y_positions[i]
        cx = (x0 + x1) / 2
        cy = 0.35 * (1 if i % 2 == 1 else -1)
        fig.add_trace(go.Scatter(
            x=[x0, cx, x1], y=[y0, cy, y1],
            mode="lines",
            line=dict(color=PALETTE["primary"], width=2,
                      shape="spline", smoothing=0.8),
            hoverinfo="none", showlegend=False, opacity=0.6,
        ))

    sizes = [40 * (scores.get(n, 1) / max_z) + 30 for n in nodes]
    colors = [PALETTE["danger"]] + [PALETTE["warning"]] * len(affected)

    fig.add_trace(go.Scatter(
        x=x_positions, y=y_positions,
        mode="markers+text",
        marker=dict(size=sizes, color=colors,
                    line=dict(width=2, color="rgba(255,255,255,0.6)")),
        text=[f"<b>{n}</b>" for n in nodes],
        textposition="middle center",
        textfont=dict(color="white", size=10),
        hovertext=[f"<b>{n}</b><br>z-score: {scores.get(n, 0):.1f}" for n in nodes],
        hoverinfo="text", showlegend=False,
    ))

    fig.update_layout(
        **_base_layout(height=200,
                       margin=dict(l=10, r=10, t=10, b=10)),
        xaxis=dict(visible=False, range=[-0.5, max(x_positions) + 0.5]),
        yaxis=dict(visible=False, range=[-1, 1]),
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 5. SIMILARITY BAR
# ═══════════════════════════════════════════════════════════════
def similarity_bar(similar: list):
    """Similarity scores with threshold bands."""
    if not similar:
        return None

    df = pd.DataFrame([{
        "id": s["id"], "similarity": s["similarity"], "cause": s["root_cause"],
    } for s in similar]).sort_values("similarity", ascending=True)

    colors = [
        PALETTE["success"] if v >= 0.75
        else PALETTE["warning"] if v >= 0.5
        else PALETTE["danger"]
        for v in df["similarity"]
    ]

    fig = go.Figure(go.Bar(
        x=df["similarity"], y=df["id"], orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=df["similarity"].apply(lambda v: f"{v:.2f}"),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Similarity: %{x:.2f}<br>Cause: %{customdata}<extra></extra>",
        customdata=df["cause"],
    ))

    for x, color, label in [(0.5, PALETTE["warning"], "ok"),
                             (0.75, PALETTE["success"], "good")]:
        fig.add_vline(x=x, line=dict(color=color, width=1, dash="dash"),
                      opacity=0.6)
        fig.add_annotation(x=x, y=1.02, yref="paper",
                           text=label, showarrow=False,
                           font=dict(color=color, size=10),
                           xanchor="left")

    fig.update_layout(
        **_base_layout(height=140 + 40 * len(df),
                       margin=dict(l=10, r=50, t=30, b=10)),
        xaxis=dict(range=[0, 1.05], title="Similarity"),
        yaxis=dict(title="", tickfont=dict(size=11)),
        showlegend=False,
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 6. EVIDENCE DONUT
# ═══════════════════════════════════════════════════════════════
def evidence_donut(report: dict):
    """Donut of evidence sources with center total."""
    ev = report.get("evidence", [])
    if not ev:
        return None

    counts = {}
    for e in ev:
        s = e.get("source", "unknown")
        counts[s] = counts.get(s, 0) + 1

    labels = list(counts.keys())
    values = list(counts.values())
    colors = [PALETTE["primary"], PALETTE["pink"],
              PALETTE["info"], PALETTE["warning"]][:len(labels)]

    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.62,
        marker=dict(colors=colors,
                    line=dict(color="rgba(255,255,255,0.15)", width=1)),
        textinfo="label+percent",
        textfont=dict(size=11),
        hovertemplate="<b>%{label}</b><br>%{value} signals (%{percent})<extra></extra>",
    ))
    fig.add_annotation(
        text=f"<b>{sum(values)}</b><br><span style='font-size:10px'>signals</span>",
        x=0.5, y=0.5, showarrow=False, font=dict(size=14),
    )
    fig.update_layout(**_base_layout(height=240,
                                     margin=dict(l=10, r=10, t=10, b=10)),
                      showlegend=False)
    return fig


# ═══════════════════════════════════════════════════════════════
# 7. ERROR RATE RIDGE
# ═══════════════════════════════════════════════════════════════
def error_rate_ridge(logs_df: pd.DataFrame):
    """Distribution of per-minute error rates per service."""
    if logs_df is None or logs_df.empty:
        return None

    agg = logs_df.groupby(["service", "minute"]).agg(
        total=("is_error", "size"),
        errors=("is_error", "sum"),
    ).reset_index()
    agg["error_rate"] = agg["errors"] / agg["total"]

    services = sorted(agg["service"].unique())
    fig = go.Figure()
    for svc in services:
        data = agg[agg["service"] == svc]["error_rate"]
        fig.add_trace(go.Violin(
            y=data, name=svc, side="positive",
            line_color=SERVICE_COLORS.get(svc, PALETTE["primary"]),
            fillcolor=SERVICE_COLORS.get(svc, PALETTE["primary"]),
            opacity=0.55, meanline_visible=True, points=False,
            hovertemplate=f"<b>{svc}</b><br>err rate: %{{y:.1%}}<extra></extra>",
        ))

    fig.update_layout(
        **_base_layout(height=280),
        yaxis=dict(title="Error rate", tickformat=".0%"),
        xaxis=dict(showticklabels=False),
        showlegend=False, violingap=0.1,
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 8. CASCADE DELAY HEATMAP
# ═══════════════════════════════════════════════════════════════
def cascade_delay_heatmap(anomalies: pd.DataFrame):
    """Time delta between first anomaly onset of each service pair."""
    if anomalies is None or anomalies.empty:
        return None

    first_onset = anomalies.groupby("service")["minute"].min()
    services = list(first_onset.index)
    n = len(services)
    if n < 2:
        return None

    z = np.zeros((n, n))
    for i, a in enumerate(services):
        for j, b in enumerate(services):
            delta = (first_onset[b] - first_onset[a]).total_seconds() / 60
            z[i, j] = delta

    fig = go.Figure(data=go.Heatmap(
        z=z, x=services, y=services,
        colorscale="RdBu_r", zmid=0,
        text=[[f"{v:+.1f}" for v in row] for row in z],
        texttemplate="%{text}",
        textfont=dict(size=10),
        colorbar=dict(title="Δ min", thickness=12),
        hovertemplate="Row: %{y}<br>Col: %{x}<br>Δ: %{z:+.1f} min<extra></extra>",
    ))
    fig.update_layout(**_base_layout(height=280 + 20 * n))
    return fig


# ═══════════════════════════════════════════════════════════════
# 9. ERROR ENTROPY TIMELINE
# ═══════════════════════════════════════════════════════════════
def error_entropy_timeline(logs_df: pd.DataFrame):
    """Shannon entropy of error distribution across services over time."""
    if logs_df is None or logs_df.empty:
        return None
    errs = logs_df[logs_df["is_error"] == 1]
    if errs.empty:
        return None

    grouped = errs.groupby(["minute", "service"]).size().unstack(fill_value=0)
    entropies = []
    for _, row in grouped.iterrows():
        total = row.sum()
        if total == 0:
            entropies.append(0)
            continue
        p = row / total
        p = p[p > 0]
        entropies.append(-(p * np.log2(p)).sum())

    df = pd.DataFrame({"minute": grouped.index, "entropy": entropies})

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["minute"], y=df["entropy"], mode="lines+markers",
        line=dict(color=PALETTE["purple"], width=2),
        marker=dict(size=7, color=PALETTE["purple"]),
        fill="tozeroy", fillcolor="rgba(168,85,247,0.15)",
        hovertemplate="%{x}<br>Entropy: %{y:.2f} bits<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout(height=260),
        xaxis_title="Time",
        yaxis=dict(title="Entropy (bits)"),
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 10. MTTR WATERFALL
# ═══════════════════════════════════════════════════════════════
def mttr_waterfall(severity_report: dict, incident: dict):
    """Waterfall showing how MTTR is composed."""
    mttr = severity_report.get("mttr", {})
    if not mttr:
        return None

    mttd = mttr.get("mttd_min", 1)
    spread = mttr.get("spread_min", 2)
    cascade_penalty = 2 * mttr.get("cascade_depth", 1)

    labels = ["Detection (MTTD)", "Spread across services",
              "Cascade penalty", "Est. total MTTR"]
    values = [mttd, max(spread - mttd, 0), cascade_penalty, 0]
    measures = ["relative", "relative", "relative", "total"]

    fig = go.Figure(go.Waterfall(
        x=labels, y=values, measure=measures,
        connector=dict(line=dict(color="rgba(129,140,248,0.5)", width=1)),
        increasing=dict(marker=dict(color=PALETTE["warning"])),
        decreasing=dict(marker=dict(color=PALETTE["success"])),
        totals=dict(marker=dict(color=PALETTE["danger"])),
        text=[f"{v:+.1f}m" if m != "total" else ""
              for v, m in zip(values, measures)],
        textposition="outside",
        hovertemplate="%{x}<br>%{y:+.1f} min<extra></extra>",
    ))
    fig.update_layout(
        **_base_layout(height=320),
        yaxis=dict(title="Minutes"),
        showlegend=False,
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 11. CALIBRATION CURVE
# ═══════════════════════════════════════════════════════════════
def calibration_curve(per_case: list):
    """Confidence calibration plot for evaluation results."""
    buckets = {0.5: [0, 0], 0.6: [0, 0], 0.7: [0, 0],
               0.8: [0, 0], 0.9: [0, 0], 1.0: [0, 0]}
    for c in per_case:
        if c.get("predicted") is None:
            continue
        correct = c.get("rank") == 1
        conf_bucket = 1.0 if correct else 0.5
        for k in sorted(buckets.keys()):
            if conf_bucket <= k:
                buckets[k][0] += 1
                buckets[k][1] += 1 if correct else 0
                break

    xs = list(buckets.keys())
    ys = [(v[1] / v[0]) if v[0] else 0 for v in buckets.values()]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers",
        line=dict(color=PALETTE["primary"], width=2),
        marker=dict(size=10), name="Model",
        hovertemplate="Confidence %{x:.1f}<br>Accuracy %{y:.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines",
        line=dict(color="#9ca3af", dash="dash"),
        name="Perfect calibration", hoverinfo="skip",
    ))
    fig.update_layout(
        **_base_layout(height=280),
        xaxis=dict(title="Stated confidence", range=[0.4, 1.05]),
        yaxis=dict(title="Observed accuracy", range=[0, 1.05]),
    )
    return fig