# src/reason.py
"""Grounded LLM reasoning with evidence verification and rule-based fallback."""
import json
import os
from pathlib import Path

from src.llm_client import call_llm


PROMPT = """You are an SRE. Analyze this incident and return STRICT JSON.

CURRENT INCIDENT:
- Window: {start} -> {end}
- Affected services (ranked): {services}
- Probable origin (from topology+trace): {origin}
- Signals: {signals}

SIMILAR HISTORICAL INCIDENTS:
{historical}

Rules:
1. root_cause MUST be one of the historical root_cause values listed above
   OR a short new label if none fit.
2. Every evidence item MUST reference a specific signal from CURRENT INCIDENT.
3. confidence must reflect how well historical matches align.

Return JSON ONLY with these keys:
{{
  "root_cause": "<string>",
  "confidence": <float 0..1>,
  "affected_services": [<list>],
  "causal_chain": [<ordered events>],
  "evidence": [{{"signal": "<string>", "source": "<anomaly_detector|rag_retriever|topology|trace>"}}],
  "recommended_action": "<string>"
}}
"""


def _verify(report: dict, incident: dict) -> dict:
    """Reject or flag reports whose evidence doesn't reference real signals."""
    signals = json.dumps(incident.get("signals", [])).lower()
    verified = []
    for e in report.get("evidence", []):
        sig = str(e.get("signal", "")).lower()
        if any(tok in signals for tok in sig.split()[:3]):
            verified.append(e)
    report["evidence"] = verified or report.get("evidence", [])
    report["_verified"] = len(verified) > 0
    return report


def analyze(incident: dict, similar: list) -> dict:
    historical = "\n".join(
        f"- {s['id']}: {s['summary']} | cause: {s['root_cause']} | "
        f"fix: {s['resolution']}"
        for s in similar
    ) or "None."

    prompt = PROMPT.format(
        start=incident["start"], end=incident["end"],
        services=", ".join(incident["affected_services"]),
        origin=incident["probable_origin"],
        signals=json.dumps(incident["signals"][:5], default=str),
        historical=historical,
    )

    text, usage = call_llm(prompt)
    if text:
        try:
            report = json.loads(text)
            report["_mode"] = "llm"
            report["_usage"] = usage
            return _verify(report, incident)
        except Exception as e:
            return _rule_based(incident, similar, error=str(e))
    return _rule_based(incident, similar)


def _rule_based(incident: dict, similar: list, error: str | None = None) -> dict:
    """Rule-based decision tree fallback — no LLM required."""
    origin = incident["probable_origin"]
    services = incident["affected_services"]
    scores = incident.get("service_scores", {})
    top = similar[0] if similar else None

    # rule: pick root cause by origin service + top similar's cause
    rule_map = {
        "db-service":      "connection_pool_saturation",
        "auth-service":    "auth_single_point_of_failure",
        "payment-service": "third_party_outage",
        "api-gateway":     "bad_deploy_upstream_unavailable",
    }
    cause = rule_map.get(origin, top["root_cause"] if top else "unknown_failure")

    downs = [s for s in services if s != origin]
    cascade = ", ".join(downs) if downs else "(no downstream impact)"

    return {
        "root_cause": cause,
        "confidence": 0.55 if top else 0.35,
        "affected_services": services,
        "causal_chain": [
            f"{origin} began emitting errors (z={scores.get(origin, 0):.1f})",
            f"Cascaded to {cascade}",
            "Downstream 5xx observed",
        ],
        "evidence": [
            {"signal": f"z-score {scores.get(origin, 0):.1f} on {origin}",
             "source": "anomaly_detector"},
            {"signal": f"matched {top['id']}" if top else "no match",
             "source": "rag_retriever"},
        ],
        "recommended_action": top["resolution"] if top else "Investigate manually",
        "_mode": "rule_based" + (f" ({error})" if error else ""),
        "_verified": True,
    }
