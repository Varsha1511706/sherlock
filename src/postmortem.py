# src/postmortem.py
"""Auto-draft post-mortem markdown."""
def draft(incident: dict, report: dict, severity: dict, changes: list) -> str:
    lines = [
        f"# Post-Mortem — {severity['severity']['sev']}",
        "",
        f"**Window:** {incident['start']} → {incident['end']}",
        f"**Origin:** `{incident['probable_origin']}`",
        f"**Root cause:** {report.get('root_cause')}",
        f"**Severity:** {severity['severity']['sev']} — {severity['severity']['label']}",
        "",
        "## Impact",
        f"- Affected services: {', '.join(incident['affected_services'])}",
        f"- Est. users: {severity['impact']['estimated_users_affected']:,}",
        f"- MTTR: {severity['mttr'].get('mttr_min', '—')} min",
        "",
        "## Timeline",
    ]
    for i, step in enumerate(report.get("causal_chain", []), 1):
        lines.append(f"{i}. {step}")
    lines += ["", "## Evidence"]
    for e in report.get("evidence", []):
        lines.append(f"- {e['signal']} _(source: {e['source']})_")
    if changes:
        lines += ["", "## Correlated changes"]
        for c in changes:
            lines.append(f"- `{c['id']}` {c['kind']} on {c['service']} "
                         f"({c['delta_min_before_incident']} min before)")
    lines += ["", "## Action items", f"- {report.get('recommended_action', '—')}"]
    return "\n".join(lines)
