"""Run the teacher (same prompt and settings as Task 1) over validation.jsonl.

The prediction is the teacher's raw reply, unchanged, so score.py sees exactly
what the teacher produced.
"""
import argparse
import json
import os
import time

import teacher


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/validation.jsonl")
    ap.add_argument("--out", default="results/teacher_validation_predictions.jsonl")
    ap.add_argument("--prompt", default="prompts/teacher_prompt.txt")
    a = ap.parse_args()
    url = os.environ["OLLAMA_URL"]
    template = teacher.load_prompt(a.prompt)
    rows = [json.loads(l) for l in open(a.input, encoding="utf-8") if l.strip()]
    t0 = time.time()
    with open(a.out, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            raw = teacher.ask(url, template, r["text"])
            f.write(json.dumps({"id": r["id"], "prediction": raw}, ensure_ascii=False) + "\n")
            if i % 20 == 0:
                print(f"{i}/{len(rows)} ({time.time() - t0:.0f}s)", flush=True)
    print(f"teacher predictions -> {a.out} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
