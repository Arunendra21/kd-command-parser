"""Command-parsing inference service.

Configuration (environment only):
  MODEL_URI       s3://<bucket>/<prefix>, e.g. s3://models/v1
  MODEL_VERSION   reported in the X-Model-Version header
  S3_ENDPOINT     SeaweedFS S3 endpoint, e.g. http://seaweedfs-s3.data:8333
  MAX_NEW_TOKENS  generation budget
  FAULT_INJECT    "1" replaces model output with "not json" (validation test)
Credentials (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) come from a k8s Secret.
"""
import logging
import os
import socket
import threading
import time
from urllib.parse import urlparse

import boto3
import torch
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from transformers import AutoModelForCausalLM, AutoTokenizer

from core import build_prompt, extract_json_text, load_schema, parse_output

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kd-service")

MODEL_URI = os.environ["MODEL_URI"]
MODEL_VERSION = os.environ["MODEL_VERSION"]
S3_ENDPOINT = os.environ["S3_ENDPOINT"]
MAX_NEW_TOKENS = int(os.environ["MAX_NEW_TOKENS"])
FAULT_INJECT = os.environ.get("FAULT_INJECT", "0") == "1"
SERVED_BY = os.environ.get("POD_NAME") or socket.gethostname()
MODEL_DIR = os.environ.get("MODEL_DIR", "/tmp/model")

KEYS, INTENTS = load_schema()
torch.set_num_threads(int(os.environ.get("TORCH_THREADS", "1")))

state = {"model": None, "tok": None, "error": None}
gen_lock = threading.Lock()
app = FastAPI()


def download_model():
    u = urlparse(MODEL_URI)
    bucket, prefix = u.netloc, u.path.strip("/")
    s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT)
    os.makedirs(MODEL_DIR, exist_ok=True)
    t0 = time.time()
    log.info("Downloading model from object storage: %s (endpoint %s)", MODEL_URI, S3_ENDPOINT)
    n = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix + "/"):
        for obj in page.get("Contents", []):
            name = obj["Key"][len(prefix) + 1:]
            if not name or "/" in name:
                continue
            s3.download_file(bucket, obj["Key"], os.path.join(MODEL_DIR, name))
            log.info("  downloaded s3://%s/%s (%d bytes)", bucket, obj["Key"], obj["Size"])
            n += 1
    if n == 0:
        raise RuntimeError(f"no objects under {MODEL_URI}")
    log.info("Model download complete: %d files in %.1fs", n, time.time() - t0)


def load_model():
    try:
        download_model()
        tok = AutoTokenizer.from_pretrained(MODEL_DIR)
        model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, torch_dtype=torch.float32)
        model.eval()
        state["tok"], state["model"] = tok, model
        log.info("Model %s loaded; ready", MODEL_VERSION)
    except Exception as e:  # keep the process alive; /readyz stays 503
        state["error"] = repr(e)
        log.exception("Model load failed")


@app.on_event("startup")
def startup():
    threading.Thread(target=load_model, daemon=True).start()


def generate(text):
    tok, model = state["tok"], state["model"]
    enc = tok(build_prompt(text), return_tensors="pt")
    with gen_lock, torch.no_grad():
        out = model.generate(
            **enc,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tok.eos_token_id,
            eos_token_id=tok.eos_token_id,
        )
    return tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)


def headers():
    return {"X-Model-Version": MODEL_VERSION, "X-Served-By": SERVED_BY}


@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "alive"}, headers=headers())


@app.get("/readyz")
async def readyz():
    if state["model"] is None:
        return JSONResponse({"status": "loading", "error": state["error"]}, status_code=503, headers=headers())
    return JSONResponse({"status": "ready"}, headers=headers())


@app.post("/parse")
def parse(body: dict, request: Request):
    if state["model"] is None:
        return JSONResponse({"error": "model_not_ready"}, status_code=503, headers=headers())
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        return JSONResponse({"error": "missing_text"}, status_code=400, headers=headers())
    raw = extract_json_text(generate(text))
    if FAULT_INJECT:
        raw = "not json"
    frame, how = parse_output(raw, text, KEYS, INTENTS)
    if how == "salvaged":
        log.warning("salvaged malformed model output for %r: %r -> %r", text, raw, frame)
    if frame is None:
        log.warning("invalid model output for %r: %r", text, raw)
        return JSONResponse({"error": "invalid_model_output"}, status_code=500, headers=headers())
    return JSONResponse(frame, headers=headers())
