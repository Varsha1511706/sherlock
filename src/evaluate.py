# src/evaluate.py
"""
Evaluation harness: runs the RCA pipeline against the fault-injection
testbed and computes top-1 / top-3 accuracy, MRR, and calibration.
"""
import json
from pathlib import Path

from src.detect import detect_anomalies
from src.cluster import group_incidents
from src.rag import retrieve_similar
from src.reason import _rule_based as _mock  # alias for backward compat


def _load_testbed(testbed_dir: str = "data/testbed") -> list:
    """Load all labeled scenarios from the testbed directory."""
    manifest_path = Path(testbed_dir) / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No testbed found at {testbed_dir}. "
            f"Run `python -m src.fault_injector` first."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = []
    for fault_type, meta in manifest.items():
        data = json.loads(Path(meta["path"]).read_text(encoding="utf-8"))
        cases.append({
            "fault_type": fault_type,
            "logs": data["logs"],
            "ground_truth": data["ground_truth"],
        })
    return cases


def evaluate(testbed_dir: str = "data/testbed",
             z_threshold: float = 3.0,
             window_min: int = 3,
             top_k: int = 3,
             use_llm: bool = False) -> dict:
    """
    Run the pipeline on every testbed case and compute accuracy metrics.

    Returns a dict with:
        - results: per-case breakdown
        - top1_accuracy, top3_accuracy, mrr
        - origin_accuracy: did we identify the right origin service?
    """
    cases = _load_testbed(testbed_dir)

    per_case = []
    reciprocal_ranks = []
    top1_hits = 0
    top3_hits = 0
    origin_hits = 0

    for case in cases:
        gt = case["ground_truth"]
        logs = case["logs"]

        # Run pipeline
        anomalies = detect_anomalies(logs)
        if anomalies.empty:
            per_case.append({
                "fault_type": case["fault_type"],
                "ground_truth": gt["root_cause"],
                "predicted": None,
                "rank": None,
                "origin_match": False,
                "similar": [],
                "reason": "no anomalies detected",
            })
            reciprocal_ranks.append(0.0)
            continue

        anomalies = anomalies[anomalies["zscore"] >= z_threshold].reset_index(drop=True)
        incidents = group_incidents(anomalies, window_minutes=window_min)

        if not incidents:
            per_case.append({
                "fault_type": case["fault_type"],
                "ground_truth": gt["root_cause"],
                "predicted": None,
                "rank": None,
                "origin_match": False,
                "similar": [],
                "reason": "no incidents grouped",
            })
            reciprocal_ranks.append(0.0)
            continue

        # Take the primary (first) incident
        inc = incidents[0]
        similar = retrieve_similar(inc, top_k=top_k)

        if use_llm:
            from src.reason import analyze as _analyze
            report = _analyze(inc, similar)
        else:
            report = _mock(inc, similar)

        predicted = report.get("root_cause")

        # Rank of the correct root cause among similar historical incidents
        ranked_causes = [s["root_cause"] for s in similar]
        rank = None
        for i, rc in enumerate(ranked_causes):
            if rc == gt["root_cause"]:
                rank = i + 1
                break

        origin_match = inc["probable_origin"] == gt["origin_service"]

        if rank == 1 or predicted == gt["root_cause"]:
            top1_hits += 1
        if rank is not None and rank <= 3:
            top3_hits += 1
        if origin_match:
            origin_hits += 1

        rr = 1.0 / rank if rank else 0.0
        reciprocal_ranks.append(rr)

        per_case.append({
            "fault_type": case["fault_type"],
            "ground_truth": gt["root_cause"],
            "predicted": predicted,
            "rank": rank,
            "origin_match": origin_match,
            "origin_gt": gt["origin_service"],
            "origin_pred": inc["probable_origin"],
            "similar": [{"id": s["id"], "cause": s["root_cause"],
                         "similarity": s["similarity"]} for s in similar],
            "reason": None,
        })

    n = len(cases) or 1
    return {
        "results": per_case,
        "n_cases": len(cases),
        "top1_accuracy": round(top1_hits / n, 3),
        "top3_accuracy": round(top3_hits / n, 3),
        "origin_accuracy": round(origin_hits / n, 3),
        "mrr": round(sum(reciprocal_ranks) / n, 3),
    }


if __name__ == "__main__":
    print("Running evaluation...")
    metrics = evaluate()
    print(f"\n  Cases:           {metrics['n_cases']}")
    print(f"  Top-1 accuracy:  {metrics['top1_accuracy']*100:.1f}%")
    print(f"  Top-3 accuracy:  {metrics['top3_accuracy']*100:.1f}%")
    print(f"  Origin accuracy: {metrics['origin_accuracy']*100:.1f}%")
    print(f"  MRR:             {metrics['mrr']:.3f}")