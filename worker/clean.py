"""Clean the teacher's shard outputs into datasets/v1/train.jsonl.

Reads every teacher/shard-*.jsonl (from S3, or from a local directory with
--local-dir), checks each record in id order and removes:
  (a) replies that are not valid JSON
  (b) replies whose keys are not exactly intent, date, time, place
  (c) replies whose intent is not one of the eight
  (d) replies with a slot value that is neither null nor text found in the command
  (e) duplicate commands among the remaining records (the smallest id is kept)
Each rejected record is counted once, under the first rule it breaks, so
input = a + b + c + d + duplicates + kept.

Every kept line holds the teacher's raw reply unchanged ("teacher_raw") and the
same frame re-serialised in one canonical line ("target"), which is what the
student is trained on. The SHA-256 of train.jsonl goes to train.sha256.
"""
import argparse
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
from core import INTENTS, KEYS, load_schema  # noqa: E402

REASONS = ["a_invalid_json", "b_wrong_keys", "c_bad_intent", "d_slot_not_in_command"]


def norm(s):
    return " ".join(s.lower().split())


def id_key(rid):
    digits = "".join(ch for ch in rid if ch.isdigit())
    return (int(digits) if digits else 0, rid)


def check(rec, keys=KEYS, intents=INTENTS):
    """Return (reason, None) for a bad record or (None, frame) for a good one."""
    try:
        obj = json.loads(rec["teacher_raw"])
    except (ValueError, TypeError):
        return "a_invalid_json", None
    if not isinstance(obj, dict) or set(obj) != set(keys) or len(obj) != len(keys):
        return "b_wrong_keys", None
    if obj["intent"] not in intents:
        return "c_bad_intent", None
    text = norm(rec["text"])
    for k in keys:
        if k == "intent" or obj[k] is None:
            continue
        v = obj[k]
        if not isinstance(v, str) or not v.strip() or norm(v) not in text:
            return "d_slot_not_in_command", None
    return None, {k: obj[k] for k in keys}


def clean(records, keys=KEYS, intents=INTENTS):
    counts = {"input": len(records), **{r: 0 for r in REASONS}, "e_duplicates": 0, "kept": 0}
    kept, seen = [], set()
    for rec in sorted(records, key=lambda r: id_key(r["id"])):
        reason, frame = check(rec, keys, intents)
        if reason:
            counts[reason] += 1
            continue
        t = norm(rec["text"])
        if t in seen:
            counts["e_duplicates"] += 1
            continue
        seen.add(t)
        kept.append({"id": rec["id"], "text": rec["text"], "teacher_raw": rec["teacher_raw"],
                     "target": json.dumps(frame, ensure_ascii=False)})
    counts["kept"] = len(kept)
    return kept, counts


def serialise(kept):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept).encode("utf-8")


def read_local(d):
    recs = []
    for p in sorted(glob.glob(os.path.join(d, "shard-*.jsonl"))):
        with open(p, encoding="utf-8") as f:
            recs += [json.loads(l) for l in f if l.strip()]
    return recs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local-dir", help="read shard-*.jsonl from here instead of s3://datasets/teacher/")
    ap.add_argument("--out-dir", default="results/datasets/v1", help="local copy of train.jsonl/train.sha256")
    ap.add_argument("--no-upload", action="store_true", help="do not write to object storage")
    ap.add_argument("--counts", default="results/clean_counts.json")
    ap.add_argument("--schema", default="data/schema.json")
    a = ap.parse_args()
    keys, intents = load_schema(a.schema)

    s3 = None
    if a.local_dir:
        records = read_local(a.local_dir)
    else:
        import s3util
        s3 = s3util.client()
        records = []
        for key in s3util.list_keys(s3, "datasets", "teacher/shard-"):
            records += [json.loads(l) for l in s3util.get_text(s3, "datasets", key).splitlines() if l.strip()]
            print(f"read s3://datasets/{key}")

    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        sys.exit("an id appears in more than one shard output")

    kept, counts = clean(records, keys, intents)
    data = serialise(kept)
    digest = hashlib.sha256(data).hexdigest()
    sha_line = f"{digest}  train.jsonl\n"

    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "train.jsonl"), "wb") as f:
        f.write(data)
    with open(os.path.join(a.out_dir, "train.sha256"), "w") as f:
        f.write(sha_line)
    counts["sha256"] = digest
    os.makedirs(os.path.dirname(a.counts) or ".", exist_ok=True)
    with open(a.counts, "w") as f:
        json.dump(counts, f, indent=2)

    if not a.no_upload:
        import s3util
        s3 = s3 or s3util.client()
        s3.put_object(Bucket="datasets", Key="v1/train.jsonl", Body=data)
        s3util.put_text(s3, "datasets", "v1/train.sha256", sha_line)
        print("wrote s3://datasets/v1/train.jsonl and s3://datasets/v1/train.sha256")

    print(json.dumps(counts, indent=2))
    total = sum(counts[r] for r in REASONS) + counts["e_duplicates"] + counts["kept"]
    assert total == counts["input"], "counts do not add up"


if __name__ == "__main__":
    main()
