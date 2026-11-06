"""Check that every command id appears in exactly one shard output (no gaps, no repeats)."""
import glob
import json
import os
import sys
from collections import Counter

shard_dir, pool_path = sys.argv[1], sys.argv[2]
pool = [json.loads(l)["id"] for l in open(pool_path, encoding="utf-8") if l.strip()]
seen = Counter()
for p in sorted(glob.glob(os.path.join(shard_dir, "shard-*.jsonl"))):
    ids = [json.loads(l)["id"] for l in open(p, encoding="utf-8") if l.strip()]
    print(f"{os.path.basename(p)}: {len(ids)} records")
    seen.update(ids)
missing = [i for i in pool if i not in seen]
repeated = [i for i, c in seen.items() if c > 1]
extra = [i for i in seen if i not in set(pool)]
print(f"pool: {len(pool)}  labelled: {sum(seen.values())}  unique: {len(seen)}")
print(f"missing: {len(missing)} {missing[:10]}")
print(f"repeated: {len(repeated)} {repeated[:10]}")
print(f"unknown ids: {len(extra)}")
sys.exit(1 if missing or repeated or extra else 0)
