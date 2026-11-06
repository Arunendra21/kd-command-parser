"""Print and save the key numbers of one Locust run (from <prefix>_stats.csv and _headers.json)."""
import csv
import json
import os
import sys

prefix = sys.argv[1]
rows = list(csv.DictReader(open(prefix + "_stats.csv")))
agg = next(r for r in rows if r["Name"] == "Aggregated")
n, fail = int(agg["Request Count"]), int(agg["Failure Count"])
out = {
    "requests": n,
    "failures": fail,
    "error_rate_pct": round(100.0 * fail / n, 3) if n else None,
    "p50_ms": float(agg["50%"]),
    "p95_ms": float(agg["95%"]),
    "rps": round(float(agg["Requests/s"]), 3),
}
hp = prefix + "_headers.json"
if os.path.exists(hp):
    h = json.load(open(hp))
    out.update(h)
    ok = sum(h["per_replica"].values())
    out["replica_share_pct"] = {k: round(100.0 * v / ok, 1) for k, v in h["per_replica"].items()} if ok else {}
json.dump(out, open(prefix + "_summary.json", "w"), indent=2)
print(json.dumps(out, indent=2))
