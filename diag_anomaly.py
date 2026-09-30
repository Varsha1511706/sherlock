from src.fault_injector import generate_with_fault
from src.detect import detect_anomalies
from src.ingest import to_dataframe

r = generate_with_fault("db_connection_pool")
gt = r["ground_truth"]
df = to_dataframe(r["logs"])

print("GROUND TRUTH:", gt)
print(f"Total logs: {len(r['logs'])}")
print()

# What did detection flag?
anomalies = detect_anomalies(r["logs"])
print(f"Anomalies detected: {len(anomalies)}")
print()

if not anomalies.empty:
    print("Anomalies by service:")
    print(anomalies.groupby("service").agg(
        count=("service", "size"),
        max_z=("zscore", "max"),
        first=("minute", "min"),
    ).to_string())
    print()
    print("Full anomaly list:")
    print(anomalies[["service", "minute", "error_rate", "zscore", "errors"]].to_string())
else:
    print("NO ANOMALIES DETECTED")
print()

# What does the raw error rate look like per service per minute?
print("Error rate per service (all minutes with errors):")
errs = df[df["is_error"] == 1].groupby(["service", "minute"]).size().reset_index(name="count")
print(errs.to_string())
