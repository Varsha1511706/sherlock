# app.py
import json
import math
from pathlib import Path
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.ingest import load_logs, to_dataframe
from src.generate_logs import generate as generate_logs
from src.fault_injector import generate_with_fault, FAULTS, generate_all_faults
from src.evaluate import evaluate
from src.pipeline import run as run_pipeline
from src import charts
from src.insights import (recurring_patterns, forecast_next_incidents,
                          slo_burn_projection, prevention_recommendations)
from src.search import semantic_search
from src.templates import mine_templates
from src.feedback import record as record_feedback
from src.alerts import dispatch as dispatch_alert
from src.postmortem import draft as draft_postmortem
from src.severity import load_slos, error_budget


st.set_page_config(page_title="AI RCA Engine", page_icon="🔍",
                   layout="wide", initial_sidebar_state="expanded")


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def sev_emoji(sev):
    return {"SEV-1": "🔴", "SEV-2": "🟠", "SEV-3": "🟡", "SEV-4": "🟢"}.get(sev, "⚪")


def sev_label(sev):
    return {"SEV-1": "CRITICAL", "SEV-2": "HIGH",
            "SEV-3": "MEDIUM", "SEV-4": "LOW"}.get(sev, "UNKNOWN")


def duration_str(s, e):
    try:
        d = max(int((pd.to_datetime(e) - pd.to_datetime(s)).total_seconds() / 60), 1)
        return f"{d} min" if d < 60 else f"{d//60}h {d%60}m"
    except Exception:
        return "—"


def burn_color(b):
    if b >= 50: return "#dc2626"
    if b >= 15: return "#f59e0b"
    if b >= 5:  return "#eab308"
    return "#22c55e"


def conf_color(c):
    if c >= 0.8: return "#22c55e"
    if c >= 0.6: return "#f59e0b"
    return "#ef4444"


def humanize(rc):
    return rc.replace("_", " ").capitalize() if rc else "Unknown"


# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ─── Global ──────────────────────────────────────────── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes shimmer {
    0%   { background-position: -1000px 0; }
    100% { background-position: 1000px 0; }
}
@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%      { opacity: 0.6; transform: scale(1.05); }
}
@keyframes dash {
    to { stroke-dashoffset: 0; }
}

.main-header{
  font-size:2.6rem;font-weight:800;
  background:linear-gradient(135deg,#818cf8 0%,#ec4899 50%,#f59e0b 100%);
  background-size:200% 200%;
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  margin-bottom:0;
  animation:shimmer 8s ease infinite;
}
.sub-header{color:#9ca3af;font-size:1.05rem;margin-top:-.5rem;margin-bottom:1.8rem}

/* ─── Hero ────────────────────────────────────────────── */
.hero-landing{
  background:linear-gradient(135deg,rgba(99,102,241,0.18) 0%,rgba(236,72,153,0.10) 100%);
  border:1px solid rgba(129,140,248,0.3);
  border-radius:20px;
  padding:2.5rem 2.4rem 2rem;
  margin-bottom:1.8rem;
  position:relative;overflow:hidden;
  animation:fadeInUp 0.5s ease-out;
}
.hero-landing::before{
  content:"";position:absolute;top:-50%;right:-10%;
  width:400px;height:400px;border-radius:50%;
  background:radial-gradient(circle,rgba(236,72,153,0.15) 0%,transparent 70%);
  pointer-events:none;
}
.hero-eyebrow{
  display:inline-block;padding:4px 12px;border-radius:20px;
  background:rgba(34,197,94,0.15);color:#22c55e;
  font-size:0.75rem;font-weight:700;letter-spacing:1px;
  text-transform:uppercase;margin-bottom:1rem;
  border:1px solid rgba(34,197,94,0.3);
}
.hero-title-big{
  font-size:2.1rem;font-weight:700;line-height:1.25;
  margin-bottom:0.8rem;color:#f9fafb;
}
.hero-sub{
  font-size:1.05rem;color:#9ca3af;
  margin-bottom:1.5rem;max-width:720px;line-height:1.5;
}
.chip-row{display:flex;gap:0.6rem;flex-wrap:wrap;margin-top:1rem;}
.chip{
  padding:6px 14px;border-radius:20px;font-size:0.83rem;font-weight:500;
  border:1px solid;display:inline-flex;align-items:center;gap:6px;
}
.chip-green {background:rgba(34,197,94,0.12);color:#22c55e;border-color:rgba(34,197,94,0.3);}
.chip-blue  {background:rgba(14,165,233,0.12);color:#0ea5e9;border-color:rgba(14,165,233,0.3);}
.chip-purple{background:rgba(168,85,247,0.12);color:#a855f7;border-color:rgba(168,85,247,0.3);}
.chip-amber {background:rgba(245,158,11,0.12);color:#f59e0b;border-color:rgba(245,158,11,0.3);}
.chip-pink  {background:rgba(236,72,153,0.12);color:#ec4899;border-color:rgba(236,72,153,0.3);}

/* ─── Stat strip ──────────────────────────────────────── */
.stat-strip{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
  gap:1rem;margin-bottom:1.8rem;
}
.stat-box{
  background:rgba(255,255,255,0.03);
  border:1px solid rgba(129,140,248,0.15);
  border-radius:12px;padding:1.1rem 1.2rem;
  transition:all 0.25s ease;
  animation:fadeInUp 0.6s ease-out backwards;
}
.stat-box:nth-child(1){animation-delay:0.05s;}
.stat-box:nth-child(2){animation-delay:0.10s;}
.stat-box:nth-child(3){animation-delay:0.15s;}
.stat-box:nth-child(4){animation-delay:0.20s;}
.stat-box:hover{
  border-color:rgba(129,140,248,0.45);
  background:rgba(255,255,255,0.05);
  transform:translateY(-2px);
}
.stat-label{
  font-size:0.7rem;color:#9ca3af;text-transform:uppercase;
  letter-spacing:1px;font-weight:600;margin-bottom:6px;
}
.stat-value{font-size:1.7rem;font-weight:800;line-height:1;}
.stat-sub{font-size:0.75rem;color:#9ca3af;margin-top:6px;}

/* ─── Pipeline flow ───────────────────────────────────── */
.pipeline-container{
  background:rgba(255,255,255,0.02);
  border:1px solid rgba(129,140,248,0.15);
  border-radius:16px;padding:1.6rem 1.6rem 1.2rem;
  margin-bottom:1.8rem;
}
.pipeline-title{
  font-size:0.75rem;color:#9ca3af;text-transform:uppercase;
  letter-spacing:1.2px;font-weight:700;margin-bottom:1.2rem;
}
.pipeline-steps{
  display:grid;grid-template-columns:repeat(6,1fr);
  gap:0.5rem;align-items:stretch;
}
.step-card{
  background:rgba(255,255,255,0.03);
  border:1px solid rgba(129,140,248,0.12);
  border-radius:10px;padding:0.9rem 0.7rem;
  text-align:center;position:relative;
  transition:all 0.25s ease;
}
.step-card:hover{
  transform:translateY(-3px);
  border-color:rgba(129,140,248,0.4);
  background:rgba(255,255,255,0.05);
}
.step-icon{
  width:44px;height:44px;border-radius:12px;
  display:flex;align-items:center;justify-content:center;
  margin:0 auto 0.6rem;font-size:1.3rem;
}
.step-num{
  font-size:0.65rem;color:#9ca3af;font-weight:700;
  letter-spacing:1px;text-transform:uppercase;margin-bottom:2px;
}
.step-name{font-size:0.85rem;font-weight:600;}
.step-desc{font-size:0.72rem;color:#9ca3af;margin-top:4px;line-height:1.3;}

/* ─── Feature grid ────────────────────────────────────── */
.feature-grid{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
  gap:1rem;margin-top:1rem;
}
.feature-card{
  background:rgba(255,255,255,0.03);
  border:1px solid rgba(129,140,248,0.15);
  border-radius:12px;padding:1.1rem 1.2rem;
  transition:all 0.2s ease;
}
.feature-card:hover{
  border-color:rgba(129,140,248,0.4);
  background:rgba(255,255,255,0.05);
}
.feature-title{
  font-weight:600;font-size:0.95rem;margin-bottom:0.35rem;
  display:flex;align-items:center;gap:0.5rem;
}
.feature-desc{font-size:0.82rem;color:#9ca3af;line-height:1.45;}

/* ─── Existing cards (kept) ───────────────────────────── */
.evidence-card{background:rgba(14,165,233,.12);border-left:3px solid #0ea5e9;padding:.65rem .95rem;border-radius:6px;margin-bottom:.5rem;font-size:.94rem}
.causal-step{background:rgba(99,102,241,.15);border-left:3px solid #818cf8;padding:.55rem .95rem;border-radius:6px;margin-bottom:.5rem;font-size:.94rem}
.similar-card{background:rgba(168,85,247,.12);border-left:3px solid #a855f7;padding:.65rem .95rem;border-radius:6px;margin-bottom:.5rem;font-size:.92rem}
.source-badge{display:inline-block;background:rgba(99,102,241,.2);padding:1px 8px;border-radius:10px;font-size:.75rem;margin-left:6px;opacity:.85}
.forecast-card{background:rgba(245,158,11,.12);border-left:3px solid #f59e0b;padding:.6rem .9rem;border-radius:6px;margin-bottom:.5rem;font-size:.92rem}
.insight-card{background:rgba(236,72,153,.12);border-left:3px solid #ec4899;padding:.6rem .9rem;border-radius:6px;margin-bottom:.5rem;font-size:.92rem}
.change-card{background:rgba(14,165,233,.10);border-left:3px solid #0ea5e9;padding:.5rem .9rem;border-radius:6px;margin-bottom:.4rem;font-size:.9rem}
.hero-card{background:linear-gradient(135deg,rgba(99,102,241,0.10) 0%,rgba(236,72,153,0.06) 100%);border:1px solid rgba(129,140,248,0.25);border-radius:14px;padding:1.4rem 1.6rem;margin-bottom:1rem}
.hero-toprow{display:flex;align-items:center;gap:1rem;margin-bottom:1rem;flex-wrap:wrap}
.hero-sev{display:inline-flex;align-items:center;gap:8px;padding:6px 14px;border-radius:20px;font-weight:700;font-size:0.85rem;letter-spacing:0.5px;color:white;box-shadow:0 2px 8px rgba(0,0,0,0.15)}
.hero-title{font-size:1.5rem;font-weight:700;margin:0}
.hero-meta{color:#9ca3af;font-size:0.85rem;margin-left:auto}
.hero-badge{display:inline-block;padding:3px 10px;border-radius:10px;font-size:0.75rem;font-weight:600;background:rgba(34,197,94,0.15);color:#22c55e;border:1px solid rgba(34,197,94,0.3)}
.kv-card{background:rgba(255,255,255,0.03);border:1px solid rgba(129,140,248,0.15);border-radius:10px;padding:0.85rem 1rem;height:100%}
.kv-label{font-size:0.7rem;text-transform:uppercase;letter-spacing:0.8px;color:#9ca3af;margin-bottom:4px;font-weight:600}
.kv-value{font-size:1.15rem;font-weight:600;line-height:1.2}
.kv-sub{font-size:0.78rem;color:#9ca3af;margin-top:2px}
.origin-pill{display:inline-block;padding:4px 12px;border-radius:8px;background:rgba(239,68,68,0.15);color:#ef4444;font-weight:600;font-size:0.95rem;border:1px solid rgba(239,68,68,0.3)}
.impact-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:0.6rem;margin-top:1rem}
.impact-cell{background:rgba(255,255,255,0.02);border-left:3px solid rgba(129,140,248,0.6);border-radius:6px;padding:0.6rem 0.8rem}
.impact-cell-label{font-size:0.68rem;text-transform:uppercase;letter-spacing:0.6px;color:#9ca3af;font-weight:600}
.impact-cell-value{font-size:1.1rem;font-weight:700;margin-top:3px}
.cascade-line{margin-top:1rem;padding:0.7rem 1rem;background:rgba(129,140,248,0.08);border-radius:8px;font-size:0.9rem}
.cascade-line b{color:#a5b4fc}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🔍 AI Root-Cause Analysis Engine</div>',
            unsafe_allow_html=True)
st.markdown('<div class="sub-header">Turn raw logs into evidence-cited root causes in under 30 seconds</div>',
            unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# RUNBOOKS + SLOs
# ═══════════════════════════════════════════════════════════════
@st.cache_data
def load_runbooks():
    p = Path("data/runbooks.json")
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}


RUNBOOKS = load_runbooks()
SLOS = load_slos()


# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ Controls")
    mode = st.radio("Mode",
                    ["📁 Analyze logs", "🧪 Inject fault", "📊 Evaluate testbed"],
                    label_visibility="collapsed")

    uploaded = None
    fault_type = None
    if mode == "📁 Analyze logs":
        src_mode = st.radio("Source", ["Synthetic", "Upload JSON"],
                            label_visibility="collapsed")
        if src_mode == "Upload JSON":
            uploaded = st.file_uploader("logs.json", type="json")
    elif mode == "🧪 Inject fault":
        fault_type = st.selectbox("Fault", list(FAULTS.keys()))

    st.divider()
    z_threshold = st.slider("EWMA z threshold", 1.5, 6.0, 2.5, 0.5)
    window_min = st.slider("Grouping window (min)", 1, 10, 3)
    top_k = st.slider("Historical matches (k)", 1, 5, 3)
    use_llm = st.toggle("Use LLM (if key)", value=True)

    st.divider()
    run = st.button("▶ Run", type="primary", use_container_width=True)

    if mode == "📁 Analyze logs":
        if st.button("🎲 Regenerate logs", use_container_width=True):
            generate_logs()
            st.success("Logs regenerated ✓")

    if mode == "📊 Evaluate testbed":
        if st.button("🛠 Build testbed", use_container_width=True):
            with st.spinner("Generating scenarios..."):
                generate_all_faults()
            st.success("Testbed ready ✓")

    with st.expander("📊 SLO configuration"):
        for svc, cfg in SLOS.items():
            st.markdown(f"- **{svc}** — SLO `{cfg['slo']*100:.1f}%` "
                        f"(crit {cfg.get('criticality', 1.0)})")


# ═══════════════════════════════════════════════════════════════
# STATE
# ═══════════════════════════════════════════════════════════════
DEFAULT_STATE = {
    "results": None, "logs_count": 0, "logs_df": None,
    "anomalies": None, "eval_metrics": None, "ground_truth": None,
    "checked_steps": {}, "last_postmortem": None,
}
for k, v in DEFAULT_STATE.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ═══════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════
if run:
    try:
        gt = None
        if mode == "📁 Analyze logs":
            with st.spinner("Loading..."):
                logs = load_logs(uploaded) if uploaded else load_logs()
        elif mode == "🧪 Inject fault":
            with st.spinner(f"Injecting: {fault_type}..."):
                r = generate_with_fault(fault_type)
                logs, gt = r["logs"], r["ground_truth"]
        else:
            logs = []

        if mode == "📊 Evaluate testbed":
            with st.spinner("Evaluating testbed scenarios..."):
                m = evaluate(z_threshold=z_threshold, window_min=window_min,
                             top_k=top_k, use_llm=use_llm)
                st.session_state.eval_metrics = m
                st.session_state.results = None
            st.rerun()
        else:
            with st.spinner("Running pipeline..."):
                out = run_pipeline(z_threshold=z_threshold,
                                   window_min=window_min,
                                   top_k=top_k,
                                   use_llm=use_llm,
                                   logs=logs)

            st.session_state.logs_count = out["logs_count"]
            st.session_state.logs_df = out["logs_df"]
            st.session_state.anomalies = out["anomalies"]
            st.session_state.results = out["results"]
            st.session_state.ground_truth = gt
            st.session_state.params = dict(z_threshold=z_threshold,
                                            window_min=window_min,
                                            top_k=top_k, use_llm=use_llm)
            if not out["results"]:
                st.warning("No incidents detected. Try lowering the z threshold.")
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.exception(e)


# ═══════════════════════════════════════════════════════════════
# EVALUATION VIEW
# ═══════════════════════════════════════════════════════════════
if st.session_state.eval_metrics:
    m = st.session_state.eval_metrics
    st.subheader("📊 Evaluation on Labeled Testbed")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Cases", m["n_cases"])
    k2.metric("Top-1", f"{m['top1_accuracy']*100:.1f}%")
    k3.metric("Top-3", f"{m['top3_accuracy']*100:.1f}%")
    k4.metric("Origin", f"{m['origin_accuracy']*100:.1f}%")
    k5.metric("MRR", f"{m['mrr']:.3f}")

    st.markdown("### Per-case")
    st.dataframe(pd.DataFrame([{
        "Fault": c["fault_type"], "Truth": c["ground_truth"],
        "Predicted": c["predicted"] or "—", "Rank": c["rank"] or "—",
        "Origin": "✅" if c["origin_match"] else "❌", "Note": c["reason"] or "",
    } for c in m["results"]]), use_container_width=True, hide_index=True)

    f = charts.calibration_curve(m["results"])
    if f:
        st.plotly_chart(f, use_container_width=True)

    if st.button("Clear"):
        st.session_state.eval_metrics = None
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# MAIN DASHBOARD
# ═══════════════════════════════════════════════════════════════
elif st.session_state.results:
    results = st.session_state.results
    anomalies = st.session_state.anomalies
    logs_df = st.session_state.logs_df

    # KPI strip
    worst_sev = max(results, key=lambda r: r["severity"]["severity"]["score"])
    max_burn = max((r["severity"]["severity"]["max_burn"] for r in results), default=0)
    total_mttr = sum(r["severity"]["mttr"].get("mttr_min", 0) for r in results)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Logs", f"{st.session_state.logs_count:,}")
    k2.metric("Incidents", len(results))
    k3.metric("Max SLO burn", f"{max_burn:.1f}×")
    k4.metric("Total MTTR est.", f"{total_mttr:.0f} min")
    k5.metric("Worst severity", worst_sev["severity"]["severity"]["sev"])

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🚨 Incidents", "📊 Fallout Analytics", "📖 Runbooks",
        "🔮 Forecast & Prevention", "🧭 Investigation",
    ])

    # ═══════════════════════════════════════════════════════════
    # TAB 1 — INCIDENTS
    # ═══════════════════════════════════════════════════════════
    with tab1:
        for idx, r in enumerate(results):
            inc, rep, sim, sev = r["incident"], r["report"], r["similar"], r["severity"]
            change_hits = r.get("changes", [])
            s = sev["severity"]
            mttr = sev["mttr"]
            impact = sev["impact"]

            sev_code = s["sev"]
            sev_lbl = sev_label(sev_code)
            sev_color = s["color"]
            sev_icon = sev_emoji(sev_code)
            dur = duration_str(inc["start"], inc["end"])
            conf = rep.get("confidence", 0)
            conf_col = conf_color(conf)
            origin = inc["probable_origin"]
            origin_z = inc.get("service_scores", {}).get(origin, 0)
            n_svc = len(inc.get("affected_services", []))
            max_burn = s["max_burn"]
            b_color = burn_color(max_burn)
            cascade_svcs = inc.get("affected_services", [])
            cascade_arrow = " → ".join(cascade_svcs) if cascade_svcs else "—"

            st.markdown(f"""
<div class="hero-card">
  <div class="hero-toprow">
    <span class="hero-sev" style="background:{sev_color};">
      {sev_icon} {sev_code} · {sev_lbl}
    </span>
    <span class="hero-title">Incident #{idx+1}</span>
    <span class="hero-badge">✅ Active</span>
    <span class="hero-meta">⏱ {dur} · {inc['start'][:16].replace('T',' ')}</span>
  </div>
</div>
""", unsafe_allow_html=True)

            rc1, rc2 = st.columns([2, 1])
            with rc1:
                st.markdown(f"""
<div class="kv-card">
  <div class="kv-label">🎯 Root Cause</div>
  <div class="kv-value">{humanize(rep.get('root_cause'))}</div>
  <div class="kv-sub">Confidence: <b style="color:{conf_col};">{conf*100:.0f}%</b> · {rep.get('_mode', 'reasoning')}</div>
</div>
""", unsafe_allow_html=True)
            with rc2:
                st.markdown(f"""
<div class="kv-card">
  <div class="kv-label">📍 Origin Service</div>
  <div class="origin-pill">{origin}</div>
  <div class="kv-sub">Anomaly score: <b>{origin_z:.1f}</b></div>
</div>
""", unsafe_allow_html=True)

            st.markdown(f"""
<div class="impact-grid">
  <div class="impact-cell" style="border-left-color:{b_color};">
    <div class="impact-cell-label">SLO Burn</div>
    <div class="impact-cell-value" style="color:{b_color};">{max_burn:.1f}×</div>
  </div>
  <div class="impact-cell">
    <div class="impact-cell-label">MTTR est.</div>
    <div class="impact-cell-value">{mttr.get('mttr_min', '—')} min</div>
  </div>
  <div class="impact-cell">
    <div class="impact-cell-label">MTTD</div>
    <div class="impact-cell-value">{mttr.get('mttd_min', '—')} min</div>
  </div>
  <div class="impact-cell">
    <div class="impact-cell-label">Blast Radius</div>
    <div class="impact-cell-value">{n_svc} svc</div>
  </div>
  <div class="impact-cell">
    <div class="impact-cell-label">Users Affected</div>
    <div class="impact-cell-value">{impact.get('estimated_users_affected', 0):,}</div>
  </div>
  <div class="impact-cell">
    <div class="impact-cell-label">Impact Score</div>
    <div class="impact-cell-value">{impact.get('impact_score', 0)}</div>
  </div>
</div>
""", unsafe_allow_html=True)

            st.markdown(f"""
<div class="cascade-line">
  🌊 <b>Cascade path:</b> {cascade_arrow}
</div>
""", unsafe_allow_html=True)

            if change_hits:
                st.markdown("**🔧 Correlated changes**")
                for c in change_hits:
                    st.markdown(
                        f'<div class="change-card">'
                        f'<b>{c["id"]}</b> — {c["kind"]} on '
                        f'<code>{c["service"]}</code> '
                        f'<span style="color:#0ea5e9;">'
                        f'({c["delta_min_before_incident"]} min before)</span>'
                        f'</div>',
                        unsafe_allow_html=True)

            with st.expander("🔍 Details — causal chain, evidence, matches", expanded=False):
                flow = charts.cascade_flow(inc, rep)
                if flow:
                    st.markdown("**🔀 Cascade flow**")
                    st.plotly_chart(flow, use_container_width=True,
                                    key=f"flow_{idx}")

                left, right = st.columns(2)
                with left:
                    st.markdown("#### 🔗 Causal chain")
                    for i, step in enumerate(rep.get("causal_chain", []), 1):
                        st.markdown(
                            f'<div class="causal-step"><b>{i}.</b> {step}</div>',
                            unsafe_allow_html=True)

                    st.markdown("#### 📎 Evidence")
                    for e in rep.get("evidence", []):
                        st.markdown(
                            f'<div class="evidence-card"><b>{e.get("signal","")}</b>'
                            f'<span class="source-badge">{e.get("source","")}</span></div>',
                            unsafe_allow_html=True)

                with right:
                    st.markdown("#### 🛠 Recommended action")
                    st.info(rep.get("recommended_action", "—"))

                    st.markdown("#### 📚 Similar historical incidents")
                    for s_ in sim:
                        sim_score = s_.get("final_score", s_.get("similarity", 0))
                        st.markdown(
                            f'<div class="similar-card"><b>{s_["id"]}</b> '
                            f'<span style="color:#a855f7;font-weight:600;">({sim_score:.2f})</span><br>'
                            f'{s_["summary"]}<br>'
                            f'<span style="color:#9ca3af;font-size:.78rem;">fix: {s_["resolution"]}</span></div>',
                            unsafe_allow_html=True)

                c1, c2 = st.columns(2)
                with c1:
                    f = charts.similarity_bar(sim)
                    if f:
                        st.plotly_chart(f, use_container_width=True,
                                        key=f"sim_{idx}")
                with c2:
                    f = charts.evidence_donut(rep)
                    if f:
                        st.plotly_chart(f, use_container_width=True,
                                        key=f"don_{idx}")

                with st.expander("🔍 Raw model output"):
                    st.json(rep)

            act1, act2, act3, act4, act5, act6 = st.columns(6)
            kb = f"fb_{idx}"
            if act1.button("👍 Correct", key=f"y_{kb}", use_container_width=True):
                record_feedback(f"incident_{idx+1}",
                                rep.get("root_cause", "unknown"), correct=True)
                st.success("Logged ✓")
            if act2.button("👎 Wrong", key=f"n_{kb}", use_container_width=True):
                record_feedback(f"incident_{idx+1}",
                                rep.get("root_cause", "unknown"), correct=False)
                st.warning("Logged.")
            if act3.button("💾 Save", key=f"s_{kb}", use_container_width=True):
                Path("data/reports").mkdir(exist_ok=True)
                out_path = Path(f"data/reports/incident_{idx+1}.json")
                out_path.write_text(json.dumps(
                    {"incident": inc, "report": rep, "similar": sim,
                     "severity": sev, "changes": change_hits},
                    indent=2, default=str))
                st.success(f"Saved → {out_path}")
            if act4.button("📄 Post-mortem", key=f"pm_{kb}", use_container_width=True):
                st.session_state.last_postmortem = draft_postmortem(
                    inc, rep, sev, change_hits)
            if act5.button("🚨 Alert", key=f"al_{kb}", use_container_width=True):
                res = dispatch_alert(inc, sev)
                st.success(f"Logged → {res['logged']}")
            if act6.button("📋 Copy RCA", key=f"c_{kb}", use_container_width=True):
                rca_text = (
                    f"Incident #{idx+1} — {sev_code} {sev_lbl}\n"
                    f"Root cause: {humanize(rep.get('root_cause'))}\n"
                    f"Origin: {origin}\n"
                    f"Cascade: {cascade_arrow}\n"
                    f"Confidence: {conf*100:.0f}%\n"
                    f"Action: {rep.get('recommended_action','')}"
                )
                st.code(rca_text, language="text")

            if st.session_state.last_postmortem:
                with st.expander("📄 Last post-mortem draft", expanded=True):
                    st.markdown(st.session_state.last_postmortem)
                    st.download_button(
                        "⬇ Download post-mortem",
                        data=st.session_state.last_postmortem,
                        file_name=f"postmortem_incident_{idx+1}.md",
                        mime="text/markdown",
                        key=f"pm_dl_{idx}")

            st.markdown("---")

    # ═══════════════════════════════════════════════════════════
    # TAB 2 — FALLOUT ANALYTICS
    # ═══════════════════════════════════════════════════════════
    with tab2:
        primary_incident = results[0]["incident"] if results else None

        st.markdown("### 🕐 Causal Timeline (Gantt)")
        g = charts.causal_gantt(anomalies, incident=primary_incident)
        if g:
            st.plotly_chart(g, use_container_width=True)
            st.caption("Bottom row = earliest anomaly. Dashed arrows show inferred causality.")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 🔥 Error heatmap")
            h = charts.error_rate_heatmap(logs_df, incident=primary_incident)
            if h:
                st.plotly_chart(h, use_container_width=True)
        with col2:
            st.markdown("### 📈 Error volume + cumulative")
            v = charts.error_volume_chart(logs_df, incident=primary_incident)
            if v:
                st.plotly_chart(v, use_container_width=True)

        st.markdown("### 📊 Error rate distribution")
        ridge = charts.error_rate_ridge(logs_df)
        if ridge:
            st.plotly_chart(ridge, use_container_width=True)
            st.caption("Wide = noisy service, thin = concentrated burst.")

        col3, col4 = st.columns(2)
        with col3:
            st.markdown("### ⏱ Cascade delay matrix")
            cd = charts.cascade_delay_heatmap(anomalies)
            if cd:
                st.plotly_chart(cd, use_container_width=True)
                st.caption("Row fired X min before column (positive = earlier).")
        with col4:
            st.markdown("### 🎲 Error entropy timeline")
            ent = charts.error_entropy_timeline(logs_df)
            if ent:
                st.plotly_chart(ent, use_container_width=True)
                st.caption("Low entropy = errors concentrated on one service.")

        st.markdown("### 💧 MTTR composition")
        if results:
            wf = charts.mttr_waterfall(results[0]["severity"], results[0]["incident"])
            if wf:
                st.plotly_chart(wf, use_container_width=True)

        st.markdown("### 📉 SLO error budget (30d window)")
        if logs_df is not None and not logs_df.empty:
            budget = error_budget(logs_df, SLOS)
            if not budget.empty:
                st.dataframe(budget, use_container_width=True, hide_index=True)

    # ═══════════════════════════════════════════════════════════
    # TAB 3 — RUNBOOKS
    # ═══════════════════════════════════════════════════════════
    with tab3:
        st.markdown("### 📖 Interactive Runbooks")
        st.caption("Check steps off as you resolve. State is per-session.")

        seen = set()
        for r in results:
            rc = r["report"].get("root_cause")
            if not rc or rc in seen:
                continue
            seen.add(rc)
            rb = RUNBOOKS.get(rc)
            with st.container(border=True):
                if rb:
                    st.markdown(f"#### {rb['title']} · `{rb['severity']}`")
                    total = len(rb["steps"])
                    done_key = f"rb_{rc}"
                    st.session_state.checked_steps.setdefault(done_key, set())

                    for i, step in enumerate(rb["steps"], 1):
                        k = f"{done_key}_step_{i}"
                        checked = st.checkbox(
                            f"**Step {i}:** {step}",
                            value=(i in st.session_state.checked_steps[done_key]),
                            key=k)
                        if checked:
                            st.session_state.checked_steps[done_key].add(i)
                        else:
                            st.session_state.checked_steps[done_key].discard(i)

                    done = len(st.session_state.checked_steps[done_key])
                    st.progress(done / total, text=f"{done}/{total} steps complete")

                    ecol1, ecol2 = st.columns([1, 3])
                    with ecol1:
                        st.download_button(
                            "⬇ Runbook",
                            data="\n".join([f"# {rb['title']} ({rb['severity']})",
                                            *[f"{i}. {s}" for i, s in enumerate(rb["steps"], 1)]]),
                            file_name=f"runbook_{rc}.md",
                            mime="text/markdown",
                            key=f"rb_dl_{rc}",
                            use_container_width=True)
                    with ecol2:
                        st.caption("Escalation: on-call SRE → DB team (if `db-service`)")
                else:
                    st.warning(f"No runbook for `{rc}`. Using LLM action:")
                    st.info(r["report"].get("recommended_action", "—"))

    # ═══════════════════════════════════════════════════════════
    # TAB 4 — FORECAST & PREVENTION
    # ═══════════════════════════════════════════════════════════
    with tab4:
        st.markdown("### 🔮 Forecast — next 30 minutes")
        fc = forecast_next_incidents(logs_df, results, horizon_min=30)
        if fc:
            for f_ in fc:
                eta = f"ETA ~{f_['eta_min']} min" if f_["eta_min"] else "watch"
                st.markdown(
                    f'<div class="forecast-card">'
                    f'<b>{f_["service"]}</b> — error rate '
                    f'{f_["current_rate"]*100:.1f}% → {f_["forecast_rate"]*100:.1f}% '
                    f'<span style="color:#f59e0b;">({eta})</span>'
                    f'</div>', unsafe_allow_html=True)
        else:
            st.success("✅ No rising trends detected — services stable.")

        st.markdown("### 📉 SLO burn projection (next 60 min)")
        proj = slo_burn_projection(logs_df, horizon_min=60)
        if not proj.empty:
            fig = px.line(proj, x="minutes_ahead", y="projected_error_rate",
                          color="service", markers=True,
                          labels={"minutes_ahead": "Minutes ahead",
                                  "projected_error_rate": "Projected error rate"})
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10),
                              yaxis_tickformat=".0%",
                              plot_bgcolor="rgba(0,0,0,0)",
                              paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("### 🛡️ Prevention recommendations")
        recs = prevention_recommendations(results)
        if recs:
            for rec in recs:
                st.markdown(
                    f'<div class="insight-card">'
                    f'<b>{humanize(rec["root_cause"])}</b> — '
                    f'seen {rec["occurrences"]}× across '
                    f'{", ".join(rec["affected_services"])}<br>'
                    f'<i>Action:</i> {rec["action"]}'
                    f'</div>', unsafe_allow_html=True)
        else:
            st.info("No recurring patterns yet.")

        st.markdown("### 🔁 Recurring root causes")
        pats = recurring_patterns(results)
        if pats:
            df = pd.DataFrame([{
                "Root cause": humanize(p["root_cause"]),
                "Occurrences": p["count"],
                "Services": ", ".join(p["services"]),
                "Prevention": p["recommendation"],
            } for p in pats])
            st.dataframe(df, use_container_width=True, hide_index=True)

    # ═══════════════════════════════════════════════════════════
    # TAB 5 — INVESTIGATION
    # ═══════════════════════════════════════════════════════════
    with tab5:
        st.markdown("### 🧭 Investigation & Semantic Search")
        st.caption("Search logs by meaning, not just keyword.")

        qcol1, qcol2 = st.columns([4, 1])
        with qcol1:
            query = st.text_input("Ask about the logs",
                                  placeholder="e.g. 'connection timeouts' or 'auth errors'")
        with qcol2:
            top_k_search = st.number_input("Results", 5, 100, 20, key="search_k")

        if query and logs_df is not None:
            with st.spinner("Searching..."):
                hits = semantic_search(logs_df, query, top_k=int(top_k_search))
            st.success(f"{len(hits)} matching log lines")
            show = hits[["timestamp", "service", "level", "message"]].copy()
            show["timestamp"] = show["timestamp"].astype(str)
            st.dataframe(show, use_container_width=True, hide_index=True)

        st.markdown("### 🧩 Message templates (Drain3)")
        if logs_df is not None and not logs_df.empty:
            tmpl = mine_templates(logs_df)
            if not tmpl.empty:
                fig = px.bar(tmpl.head(15), x="count", y="template",
                             orientation="h", color="count",
                             color_continuous_scale="Blues")
                fig.update_layout(height=420,
                                  margin=dict(l=10, r=10, t=20, b=10),
                                  coloraxis_showscale=False,
                                  plot_bgcolor="rgba(0,0,0,0)",
                                  paper_bgcolor="rgba(0,0,0,0)",
                                  yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("### 🔬 Drill into an incident")
        for idx, r in enumerate(results):
            inc = r["incident"]
            with st.expander(f"Incident #{idx+1} — {inc['start']} → {inc['end']}"):
                window = logs_df[
                    (logs_df["minute"] >= pd.to_datetime(inc["start"])) &
                    (logs_df["minute"] <= pd.to_datetime(inc["end"]))
                ]
                st.caption(f"{len(window)} log lines in window")
                errs = window[window["is_error"] == 1].head(50)
                if not errs.empty:
                    st.markdown("**Error lines (first 50):**")
                    st.dataframe(
                        errs[["timestamp", "service", "level", "message"]]
                        .assign(timestamp=lambda d: d["timestamp"].astype(str)),
                        use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# LANDING PAGE
# ═══════════════════════════════════════════════════════════════
else:
    # ── Hero band ─────────────────────────────────────────────
    st.markdown("""
<div class="hero-landing">
  <span class="hero-eyebrow">⚡ Production-grade AIOps</span>
  <div class="hero-title-big">
    Detect incidents, attribute root causes,<br>
    and cite evidence — automatically.
  </div>
  <div class="hero-sub">
    A complete pipeline that ingests distributed logs, detects anomalies with
    EWMA control charts, clusters incidents by trace + topology, retrieves
    similar historical cases, and generates evidence-cited root-cause reports
    with runbooks and post-mortems.
  </div>
  <div class="chip-row">
    <span class="chip chip-green">✅ EWMA detection</span>
    <span class="chip chip-blue">📈 Poisson change-point</span>
    <span class="chip chip-purple">🔗 Topology causality</span>
    <span class="chip chip-amber">📚 Cosine RAG + decay</span>
    <span class="chip chip-pink">🧠 Grounded LLM</span>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Stat strip ────────────────────────────────────────────
    st.markdown("""
<div class="stat-strip">
  <div class="stat-box">
    <div class="stat-label">Log lines (sample)</div>
    <div class="stat-value">5,106</div>
    <div class="stat-sub">Multi-service, timestamped, traced</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Incidents detected</div>
    <div class="stat-value">3</div>
    <div class="stat-sub">db, auth, payment</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Max SLO burn</div>
    <div class="stat-value" style="color:#f59e0b;">12.4×</div>
    <div class="stat-sub">Against 99.9% target</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Est. MTTR</div>
    <div class="stat-value" style="color:#22c55e;">8 min</div>
    <div class="stat-sub">With cascade-weighted penalty</div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Pipeline flow ─────────────────────────────────────────
    st.markdown("""
<div class="pipeline-container">
  <div class="pipeline-title">🔄 Pipeline — six stages, end to end</div>
  <div class="pipeline-steps">
    <div class="step-card">
      <div class="step-icon" style="background:rgba(99,102,241,0.25);">📥</div>
      <div class="step-num">STEP 1</div>
      <div class="step-name">Ingest</div>
      <div class="step-desc">Multi-format logs → normalized schema</div>
    </div>
    <div class="step-card">
      <div class="step-icon" style="background:rgba(14,165,233,0.25);">🔎</div>
      <div class="step-num">STEP 2</div>
      <div class="step-name">Detect</div>
      <div class="step-desc">EWMA control chart + Poisson change-point</div>
    </div>
    <div class="step-card">
      <div class="step-icon" style="background:rgba(168,85,247,0.25);">🧩</div>
      <div class="step-num">STEP 3</div>
      <div class="step-name">Cluster</div>
      <div class="step-desc">Adaptive windows + trace-ID linkage</div>
    </div>
    <div class="step-card">
      <div class="step-icon" style="background:rgba(236,72,153,0.25);">🔗</div>
      <div class="step-num">STEP 4</div>
      <div class="step-name">Attribute</div>
      <div class="step-desc">Topology + trace causality ranking</div>
    </div>
    <div class="step-card">
      <div class="step-icon" style="background:rgba(245,158,11,0.25);">📚</div>
      <div class="step-num">STEP 5</div>
      <div class="step-name">Retrieve</div>
      <div class="step-desc">Cosine RAG over historical incidents</div>
    </div>
    <div class="step-card">
      <div class="step-icon" style="background:rgba(34,197,94,0.25);">🎯</div>
      <div class="step-num">STEP 6</div>
      <div class="step-name">Explain</div>
      <div class="step-desc">Evidence-cited root cause + runbook</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── How to start ──────────────────────────────────────────
    st.markdown("#### 🚀 Get started")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
<div class="feature-card">
  <div class="feature-title">📁 Analyze logs</div>
  <div class="feature-desc">Load the synthetic dataset or upload your own JSON logs. Best for first look.</div>
</div>
""", unsafe_allow_html=True)
    with c2:
        st.markdown("""
<div class="feature-card">
  <div class="feature-title">🧪 Inject fault</div>
  <div class="feature-desc">Pick one of 6 labeled failure modes (db pool, memory leak, network latency, etc.) and see the pipeline in action.</div>
</div>
""", unsafe_allow_html=True)
    with c3:
        st.markdown("""
<div class="feature-card">
  <div class="feature-title">📊 Evaluate testbed</div>
  <div class="feature-desc">Run the full benchmark: top-1, top-3, origin accuracy, MRR, and calibration curve.</div>
</div>
""", unsafe_allow_html=True)

    # ── What you get ──────────────────────────────────────────
    st.markdown("#### 🎁 What you get after running")
    st.markdown("""
<div class="feature-grid">
  <div class="feature-card">
    <div class="feature-title">🚨 Incident hero cards</div>
    <div class="feature-desc">SEV class, root cause, causal chain, correlated deploys, blast radius, and one-click post-mortem.</div>
  </div>
  <div class="feature-card">
    <div class="feature-title">📊 Fallout analytics</div>
    <div class="feature-desc">Gantt timeline, error heatmap, cascade-delay matrix, entropy curve, MTTR waterfall, SLO budget.</div>
  </div>
  <div class="feature-card">
    <div class="feature-title">📖 Interactive runbooks</div>
    <div class="feature-desc">Auto-selected from detected root cause. Track steps, download as Markdown.</div>
  </div>
  <div class="feature-card">
    <div class="feature-title">🔮 Forecast & prevention</div>
    <div class="feature-desc">Rising trends, SLO burn projection, recurring pattern detection.</div>
  </div>
  <div class="feature-card">
    <div class="feature-title">🧭 Investigation</div>
    <div class="feature-desc">Semantic log search with sentence-transformers and Drain3 template mining.</div>
  </div>
  <div class="feature-card">
    <div class="feature-title">🔔 Alerts & post-mortems</div>
    <div class="feature-desc">Webhook dispatch logs + auto-drafted markdown ready to paste into your incident tracker.</div>
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("")
    st.info("👈 **Pick a mode in the sidebar** and click **▶ Run** to begin.")