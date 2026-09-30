# src/templates.py
"""Log template mining with Drain3."""
import pandas as pd
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig


def mine_templates(logs_df: pd.DataFrame) -> pd.DataFrame:
    """Return unique templates with counts and sample."""
    if logs_df is None or logs_df.empty:
        return pd.DataFrame(columns=["template_id", "template", "count", "level"])

    cfg = TemplateMinerConfig()
    cfg.drain_sim_th = 0.4
    cfg.drain_depth = 6
    cfg.profiling_enabled = False
    miner = TemplateMiner(config=cfg)

    rows = []
    for _, r in logs_df.iterrows():
        res = miner.add_log_message(r["message"])
        rows.append({
            "template_id": res["cluster_id"],
            "template": res["template_mined"],
            "service": r["service"],
            "level": r["level"],
        })

    tdf = pd.DataFrame(rows)
    summary = (tdf.groupby(["template_id", "template"])
                  .agg(count=("template", "size"),
                       services=("service", lambda s: ", ".join(sorted(set(s)))),
                       level=("level", lambda s: s.mode().iloc[0] if not s.mode().empty else "INFO"))
                  .reset_index()
                  .sort_values("count", ascending=False))
    return summary
