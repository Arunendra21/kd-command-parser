"""Create the buckets and upload the dataset (and any committed pipeline outputs).

Run inside the kd-worker image (it has boto3) with S3_ENDPOINT pointing at SeaweedFS.
"""
import glob
import os
import sys
import time

sys.path.insert(0, "/repo/worker")
import s3util  # noqa: E402

os.chdir("/repo")
s3 = s3util.client()
for attempt in range(30):
    try:
        existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
        break
    except Exception as e:  # SeaweedFS may still be starting
        print(f"waiting for S3 ({e.__class__.__name__})")
        time.sleep(3)
else:
    sys.exit("S3 endpoint not reachable")

for b in ("datasets", "models"):
    if b not in existing:
        s3.create_bucket(Bucket=b)
        print(f"created bucket {b}")

s3.upload_file("data/commands_pool.jsonl", "datasets", "commands_pool.jsonl")
print("uploaded s3://datasets/commands_pool.jsonl")

# Pipeline outputs that are committed as evidence are restored on a fresh cluster,
# unless the bucket already has them.
for path in sorted(glob.glob("results/teacher_shards/shard-*.jsonl")):
    key = "teacher/" + os.path.basename(path)
    if not s3util.exists(s3, "datasets", key):
        s3.upload_file(path, "datasets", key)
        print(f"restored s3://datasets/{key}")
for name in ("train.jsonl", "train.sha256"):
    path = f"results/datasets/v1/{name}"
    if os.path.exists(path) and not s3util.exists(s3, "datasets", f"v1/{name}"):
        s3.upload_file(path, "datasets", f"v1/{name}")
        print(f"restored s3://datasets/v1/{name}")

for b in ("datasets", "models"):
    print(f"s3://{b}: {s3util.list_keys(s3, b, '')}")
