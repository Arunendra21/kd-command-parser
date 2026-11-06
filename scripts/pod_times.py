"""Creation -> Ready seconds for kd-service pods created after a given epoch time (stdin: kubectl get pods -o json)."""
import json
import sys
from datetime import datetime, timezone

since = float(sys.argv[1])
p = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
for pod in json.load(sys.stdin)["items"]:
    created = p(pod["metadata"]["creationTimestamp"])
    if created < since - 1:
        continue
    ready = [c for c in pod["status"].get("conditions", []) if c["type"] == "Ready" and c["status"] == "True"]
    if ready:
        print(pod["metadata"]["name"], int(p(ready[0]["lastTransitionTime"]) - created))
