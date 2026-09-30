# src/pipeline.py
"""End-to-end async-friendly pipeline (sync interface)."""
from src.ingest import load_logs, to_dataframe
from src.detect import detect_anomalies
from src.cluster import group_incidents
from src.rag import retrieve_similar
from src.reason import analyze
from src.causality import load_topology, rank_causes
from src.severity import full_report as severity_report, load_slos
from src.changes import load_changes, correlate as correlate_changes


def run(z_threshold: float = 3.0, window_min: int = 3, top_k: int = 3,
        use_llm: bool = True, logs: list | None = None) -> dict:
    logs = logs or load_logs()
    df = to_dataframe(logs)
    anomalies = detect_anomalies(logs)
    if not anomalies.empty:
        anomalies = anomalies[anomalies["zscore"] >= z_threshold].reset_index(drop=True)

    incidents = group_incidents(anomalies, window_minutes=window_min, logs_df=df)

    topology = load_topology()
    slos = load_slos()
    changes = load_changes()

    out = []
    for inc in incidents:
        ranking = rank_causes(inc, df, topology)
        if ranking:
            inc["probable_origin"] = ranking[0]["service"]
            inc["origin_ranking"] = ranking

        similar = retrieve_similar(inc, top_k=top_k)
        report = analyze(inc, similar) if use_llm else None
        from src.reason import _rule_based
        report = report or _rule_based(inc, similar)
        sev = severity_report(df, anomalies, inc, slos=slos)
        change_hits = correlate_changes(inc, changes)

        out.append({
            "incident": inc,
            "report": report,
            "similar": similar,
            "severity": sev,
            "changes": change_hits,
        })

    return {
        "logs_count": len(logs),
        "anomalies": anomalies,
        "logs_df": df,
        "results": out,
    }
