import json
from src.fault_injector import generate_with_fault
from src.pipeline import run as run_pipeline

# Regenerate the exact same fault you tested with
fault = "db_connection_pool"   # <-- change if you used a different one
r = generate_with_fault(fault)
print("GROUND TRUTH:")
print(f"  root_cause = {r['ground_truth']['root_cause']}")
print(f"  origin     = {r['ground_truth']['origin_service']}")
print(f"  affected   = {r['ground_truth']['affected_services']}")
print()

out = run_pipeline(use_llm=False, logs=r["logs"])
print("PIPELINE OUTPUT:")
print(f"  incidents detected = {len(out['results'])}")
print(f"  anomalies          = {len(out['anomalies'])}")
print()
for i, res in enumerate(out["results"]):
    inc = res["incident"]
    print(f"Incident #{i+1}:")
    print(f"  origin           = {inc['probable_origin']}")
    print(f"  affected         = {inc['affected_services']}")
    print(f"  service_scores   = {inc['service_scores']}")
    print(f"  predicted cause  = {res['report']['root_cause']}")
    print()
