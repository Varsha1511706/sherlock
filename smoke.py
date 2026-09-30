from src.pipeline import run

out = run(use_llm=False)
print(f"Logs:      {out['logs_count']}")
print(f"Anomalies: {len(out['anomalies'])}")
print(f"Incidents: {len(out['results'])}")
print()
for r in out["results"]:
    inc = r["incident"]
    rep = r["report"]
    sev = r["severity"]["severity"]
    changes = r.get("changes", [])
    print(f"  {inc['start']}  origin={inc['probable_origin']}  "
          f"cause={rep['root_cause']}  sev={sev['sev']}  "
          f"changes={len(changes)}")
