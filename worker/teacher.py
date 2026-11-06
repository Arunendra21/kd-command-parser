"""Teacher client: phi3.5 served by Ollama, fixed settings (temperature 0, seed 42)."""
import os
import time

import requests

TEACHER_MODEL = os.environ.get("TEACHER_MODEL", "phi3.5")
OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 128}


def load_prompt(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def render(template, text):
    return template.replace("{command}", text)


def ask(ollama_url, template, text, retries=6, timeout=300):
    """Return the teacher's reply text exactly as generated."""
    payload = {
        "model": TEACHER_MODEL,
        "prompt": render(template, text),
        "stream": False,
        "format": "json",
        "options": OPTIONS,
        "keep_alive": "60m",
    }
    delay = 2
    for attempt in range(retries):
        try:
            r = requests.post(ollama_url.rstrip("/") + "/api/generate", json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()["response"]
        except (requests.RequestException, KeyError, ValueError) as e:
            if attempt == retries - 1:
                raise
            print(f"teacher call failed ({e}); retry in {delay}s", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 60)
