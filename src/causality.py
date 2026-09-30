# src/causality.py
"""
Causal inference over incidents using:
  1. Trace ID linkage (strongest signal)
  2. Service topology (imported graph)
  3. Temporal ordering (weakest, fallback)
"""
import json
from pathlib import Path
from collections import defaultdict


def load_topology(path: str = "data/topology.json") -> dict:
    p = Path(path)
    if not p.exists():
        return {"nodes": [], "edges": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _downstream_of(topology: dict, origin: str) -> list:
    """BFS over directed edges from origin."""
    adj = defaultdict(list)
    for e in topology.get("edges", []):
        adj[e["from"]].append(e["to"])
    visited, queue = set(), [origin]
    while queue:
        n = queue.pop()
        for m in adj[n]:
            if m not in visited:
                visited.add(m)
                queue.append(m)
    return list(visited)


def rank_causes(incident: dict, logs_df, topology: dict) -> list:
    """
    Return services ranked as probable origins, with evidence kind:
      trace_link  -> same trace_id spans services, earliest wins
      topology    -> downstream services present, upstream wins
      temporal    -> earliest onset wins
    """
    affected = incident.get("affected_services", [])
    first_onset = incident.get("first_onset", {})

    ranking = []

    # 1. trace_id based
    if logs_df is not None and "trace_id" in logs_df.columns:
        window = logs_df[logs_df["service"].isin(affected)]
        window = window.dropna(subset=["trace_id"])
        for trace, grp in window.groupby("trace_id"):
            if grp["service"].nunique() > 1:
                svc_first = (grp.sort_values("timestamp")
                                .groupby("service")["timestamp"].min())
                earliest = svc_first.idxmin()
                for svc in affected:
                    ranking.append({
                        "service": svc,
                        "evidence": "trace_link",
                        "weight": 3.0 if svc == earliest else 1.0,
                    })
                break

    # 2. topology based
    for candidate in affected:
        downstream = set(_downstream_of(topology, candidate))
        match = len(downstream & set(affected))
        if match > 0:
            ranking.append({
                "service": candidate,
                "evidence": "topology",
                "weight": 2.0 * match,
            })

    # 3. temporal
    for svc, ts in first_onset.items():
        ranking.append({"service": svc, "evidence": "temporal", "weight": 1.0})

    agg = defaultdict(float)
    for r in ranking:
        agg[r["service"]] += r["weight"]

    return sorted(
        [{"service": s, "score": round(w, 2)} for s, w in agg.items()],
        key=lambda x: -x["score"],
    )
