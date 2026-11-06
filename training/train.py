"""Sequence-level knowledge distillation: fine-tune Pythia-70M on teacher replies.

Each example is
    Command: <the command>
    JSON: <the teacher's JSON reply><eos>
and the loss is computed on the JSON reply only (the prompt tokens are masked).

Usage:  python training/train.py --config training/config.yaml [--subset 50]
All hyper-parameters come from the config file; the seed is fixed in code below.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import sys
import time

import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
from core import build_prompt  # noqa: E402


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def load_records(cfg, subset):
    path = cfg["data_path"]
    data = open(path, "rb").read()
    sha_path = cfg.get("data_sha256_path")
    if sha_path and os.path.exists(sha_path):
        expected = open(sha_path).read().split()[0]
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            sys.exit(f"{path}: sha256 {actual} does not match {sha_path}")
    rows = [json.loads(l) for l in data.decode("utf-8").splitlines() if l.strip()]
    n = subset if subset else cfg["train_records"]
    return rows[: min(n, cfg["train_records"])]


def encode(tok, rows, max_len):
    examples = []
    for r in rows:
        p = tok(build_prompt(r["text"]))["input_ids"]
        t = tok(" " + r["target"])["input_ids"] + [tok.eos_token_id]
        ids = (p + t)[:max_len]
        labels = ([-100] * len(p) + t)[:max_len]
        examples.append((ids, labels))
    return examples


def collate(batch, pad_id):
    n = max(len(ids) for ids, _ in batch)
    input_ids = torch.full((len(batch), n), pad_id)
    labels = torch.full((len(batch), n), -100)
    attn = torch.zeros((len(batch), n), dtype=torch.long)
    for i, (ids, lab) in enumerate(batch):
        input_ids[i, : len(ids)] = torch.tensor(ids)
        labels[i, : len(lab)] = torch.tensor(lab)
        attn[i, : len(ids)] = 1
    return {"input_ids": input_ids, "attention_mask": attn, "labels": labels}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="training/config.yaml")
    ap.add_argument("--subset", type=int, default=0, help="train on the first N records only")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config))

    seed = int(cfg["seed"])
    set_seed(seed)
    torch.set_num_threads(int(os.environ.get("TRAIN_THREADS", os.cpu_count() or 1)))

    out_dir = cfg["output_dir"] if not a.subset else f"artifacts/subset{a.subset}"
    loss_csv = cfg["loss_csv"] if not a.subset else f"training/loss_subset{a.subset}.csv"

    rows = load_records(cfg, a.subset)
    print(f"training {cfg['version']} on {len(rows)} records from {cfg['data_path']}", flush=True)
    print(f"torch {torch.__version__}, config library_versions: {cfg.get('library_versions')}", flush=True)

    tok = AutoTokenizer.from_pretrained(cfg["base_model"], revision=cfg.get("base_model_revision", "main"))
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], revision=cfg.get("base_model_revision", "main"))
    model.train()

    examples = encode(tok, rows, int(cfg["max_seq_length"]))
    g = torch.Generator().manual_seed(seed)
    loader = DataLoader(examples, batch_size=int(cfg["batch_size"]), shuffle=True, generator=g,
                        collate_fn=lambda b: collate(b, tok.pad_token_id))
    epochs = int(cfg["epochs"])
    opt = torch.optim.AdamW(model.parameters(), lr=float(cfg["learning_rate"]),
                            weight_decay=float(cfg.get("weight_decay", 0.0)))
    total = epochs * len(loader)
    sched = get_linear_schedule_with_warmup(opt, int(total * float(cfg.get("warmup_ratio", 0.0))), total)

    os.makedirs(os.path.dirname(loss_csv) or ".", exist_ok=True)
    with open(loss_csv, "w", newline="") as f:
        csv.writer(f).writerow(["epoch", "train_loss", "seconds"])
    t_start = time.time()
    for epoch in range(1, epochs + 1):
        t0, total_loss, steps = time.time(), 0.0, 0
        for batch in loader:
            loss = model(**batch).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            total_loss += loss.item()
            steps += 1
        mean = total_loss / steps
        with open(loss_csv, "a", newline="") as f:
            csv.writer(f).writerow([epoch, f"{mean:.6f}", f"{time.time() - t0:.1f}"])
        print(f"epoch {epoch}/{epochs} loss {mean:.4f} ({time.time() - t0:.0f}s)", flush=True)

    model.eval()
    os.makedirs(out_dir, exist_ok=True)
    model.save_pretrained(out_dir, safe_serialization=True)
    tok.save_pretrained(out_dir)
    info = {
        "version": cfg["version"] if not a.subset else f"subset{a.subset}",
        "base_model": cfg["base_model"],
        "train_records": len(rows),
        "train_sha256": hashlib.sha256(open(cfg["data_path"], "rb").read()).hexdigest(),
        "seed": seed,
        "epochs": epochs,
        "learning_rate": cfg["learning_rate"],
        "batch_size": cfg["batch_size"],
        "max_seq_length": cfg["max_seq_length"],
        "torch": torch.__version__,
        "transformers": __import__("transformers").__version__,
        "train_seconds": round(time.time() - t_start, 1),
    }
    with open(os.path.join(out_dir, "version.json"), "w") as f:
        json.dump(info, f, indent=2)
    print(f"saved model and tokenizer to {out_dir}; loss per epoch in {loss_csv}")


if __name__ == "__main__":
    main()
