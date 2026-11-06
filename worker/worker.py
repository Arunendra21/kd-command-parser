"""Teacher-labelling worker (one shard).

Env: SHARD_INDEX (from 0), SHARD_COUNT, OLLAMA_URL, S3_ENDPOINT,
     AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (from a Secret),
     PROMPT_PATH (default prompts/teacher_prompt.txt).
Takes the commands whose 0-based line number % SHARD_COUNT == SHARD_INDEX and
writes {"id", "text", "teacher_raw"} lines to s3://datasets/teacher/shard-<i>.jsonl.
Progress is checkpointed to the same object, so a restarted pod resumes.
"""
import json
import os
import sys
import time

import s3util
import teacher

BUCKET = "datasets"
POOL_KEY = "commands_pool.jsonl"
CHECKPOINT_EVERY = 25


def shard_lines(lines, index, count):
    return [line for n, line in enumerate(lines) if n % count == index]


def main():
    index = int(os.environ["SHARD_INDEX"])
    count = int(os.environ["SHARD_COUNT"])
    if not 0 <= index < count:
        sys.exit(f"SHARD_INDEX {index} out of range for SHARD_COUNT {count}")
    url = os.environ["OLLAMA_URL"]
    template = teacher.load_prompt(os.environ.get("PROMPT_PATH", "prompts/teacher_prompt.txt"))
    out_key = f"teacher/shard-{index}.jsonl"

    s3 = s3util.client()
    pool = [l for l in s3util.get_text(s3, BUCKET, POOL_KEY).splitlines() if l.strip()]
    mine = [json.loads(l) for l in shard_lines(pool, index, count)]
    print(f"shard {index}/{count}: {len(mine)} of {len(pool)} commands -> s3://{BUCKET}/{out_key}", flush=True)

    done = []
    if s3util.exists(s3, BUCKET, out_key):
        done = [l for l in s3util.get_text(s3, BUCKET, out_key).splitlines() if l.strip()]
        print(f"resuming: {len(done)} already labelled", flush=True)
    done_ids = {json.loads(l)["id"] for l in done}

    t0 = time.time()
    for i, rec in enumerate(mine, 1):
        if rec["id"] in done_ids:
            continue
        raw = teacher.ask(url, template, rec["text"])
        done.append(json.dumps({"id": rec["id"], "text": rec["text"], "teacher_raw": raw}, ensure_ascii=False))
        if len(done) % CHECKPOINT_EVERY == 0 or i == len(mine):
            s3util.put_text(s3, BUCKET, out_key, "\n".join(done) + "\n")
            print(f"[shard {index}] {len(done)}/{len(mine)} labelled, {time.time() - t0:.0f}s", flush=True)
    s3util.put_text(s3, BUCKET, out_key, "\n".join(done) + "\n")
    print(f"shard {index} complete: {len(done)} records in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
