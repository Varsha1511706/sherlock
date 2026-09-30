from src.fault_injector import generate_with_fault
from src.ingest import to_dataframe
from src.detect import detect_anomalies
from src.cluster import group_incidents
from src.causality import load_topology, rank_causes

r = generate_with_fault("db_connection_pool")
df = to_dataframe(r["logs"])
anomalies = detect_anomalies(r["logs"])

print(f"Total logs:      {len(r['logs'])}")
print(f"Total anomalies: {len(anomalies)}")
print()

if not anomalies.empty:
    print("Anomalies by service:")
    print(anomalies.groupby("service").agg(
        count=("service", "size"),
        max_z=("zscore", "max"),
        first=("minute", "min"),
    ).to_string())
    print()
    print("All anomalies:")
    print(anomalies[["service", "minute", "error_rate", "zscore", "errors"]].to_string())

incidents = group_incidents(anomalies, logs_df=df)
if incidents:
    inc = incidents[0]
    print()
    print(f"Incident origin (from clustering): {inc['probable_origin']}")
    print(f"Affected services: {inc['affected_services']}")
    print()

    topo = load_topology()
    ranking = rank_causes(inc, df, topo)
    print("Origin ranking:")
    for entry in ranking:
        print(f"  {entry['service']:20s} score={entry['score']}")
    print()
    print(f"Final picked origin: {ranking[0]['service']}")
    print(f"Ground truth:        {r['ground_truth']['origin_service']}")
