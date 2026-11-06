"""Cost per 1,000 requests from the rate card, the pod limits and a measured Locust run.

cost/1000 = (hourly cost of all running replicas / requests served per hour) * 1000
Each replica is billed for its CPU limit and memory limit.
"""
import json
import re
import sys

summary, deploy, card = json.load(open(sys.argv[1])), open(sys.argv[2]).read(), json.load(open(sys.argv[3]))
replicas = int(sys.argv[4]) if len(sys.argv) > 4 else len(summary.get("per_replica", {})) or 1
lim = re.search(r"limits:\s*\{cpu:\s*\"?([\d.m]+)\"?,\s*memory:\s*(\d+)(Gi|Mi)", deploy)
cpu = float(lim.group(1)[:-1]) / 1000 if lim.group(1).endswith("m") else float(lim.group(1))
mem = float(lim.group(2)) / (1 if lim.group(3) == "Gi" else 1024)
per_replica = cpu * card["vcpu_hour"] + mem * card["gib_memory_hour"]
hourly = replicas * per_replica
per_hour = summary["rps"] * 3600
cost = hourly / per_hour * 1000
print(f"replicas={replicas}  cpu_limit={cpu} vCPU  mem_limit={mem} GiB")
print(f"per replica: {cpu} x {card['vcpu_hour']} + {mem} x {card['gib_memory_hour']} = {per_replica:.4f} {card['currency']}/h")
print(f"all replicas: {replicas} x {per_replica:.4f} = {hourly:.4f} {card['currency']}/h")
print(f"requests/hour: {summary['rps']} rps x 3600 = {per_hour:.1f}")
print(f"cost per 1000 requests = {hourly:.4f} / {per_hour:.1f} x 1000 = {cost:.4f} {card['currency']}")
