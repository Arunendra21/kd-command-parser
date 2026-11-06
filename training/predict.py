"""Run a student model (local dir or Hugging Face name) over a JSONL file of commands.

Writes {"id", "prediction"} lines for tools/score.py. Decoding and output
extraction are identical to the deployed service (service/core.py).
"""
import argparse
import json
import os
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
from core import build_prompt, extract_json_text, parse_output  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="model directory or HF id (e.g. EleutherAI/pythia-70m)")
    ap.add_argument("--input", default="data/validation.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-new-tokens", type=int, default=64)
    ap.add_argument("--strict", action="store_true",
                    help="write the raw extracted text only (no salvage step); default mirrors the service")
    a = ap.parse_args()

    torch.manual_seed(42)
    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForCausalLM.from_pretrained(a.model).eval()
    rows = [json.loads(l) for l in open(a.input, encoding="utf-8") if l.strip()]
    t0 = time.time()
    counts = {}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            enc = tok(build_prompt(r["text"]), return_tensors="pt")
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=a.max_new_tokens, do_sample=False,
                                     pad_token_id=tok.eos_token_id, eos_token_id=tok.eos_token_id)
            gen = tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)
            raw = extract_json_text(gen)
            frame, how = parse_output(raw, r["text"])
            pred = raw if a.strict or frame is None else json.dumps(frame)
            counts[how] = counts.get(how, 0) + 1
            f.write(json.dumps({"id": r["id"], "prediction": pred}, ensure_ascii=False) + "\n")
    print(f"{len(rows)} predictions from {a.model} -> {a.out} in {time.time() - t0:.1f}s; output parsing: {counts}"
          + (" (strict mode: salvaged outputs written raw)" if a.strict else ""))


if __name__ == "__main__":
    main()
