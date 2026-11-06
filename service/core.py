"""Shared logic: prompt format, output extraction and schema validation.

Used by the inference service, the training/evaluation scripts and the tests,
so that training, offline evaluation and the deployed service all treat model
output in exactly the same way.
"""
import json
import os

KEYS = ["intent", "date", "time", "place"]
INTENTS = [
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events",
]


def load_schema(path=None):
    """Return (keys, intents) from schema.json, falling back to the spec values."""
    path = path or os.environ.get("SCHEMA_PATH", "")
    if not path or not os.path.exists(path):
        return list(KEYS), list(INTENTS)
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)
    keys = schema.get("keys") or schema.get("required") or list(KEYS)
    if isinstance(keys, dict):
        keys = list(keys)
    intents = schema.get("intents") or list(INTENTS)
    if isinstance(intents, dict):
        intents = list(intents)
    return list(keys), list(intents)


def build_prompt(text):
    """Student input format. The target JSON follows after 'JSON: '."""
    return f"Command: {text.strip()}\nJSON:"


def extract_json_text(generated):
    """Cut the generated continuation down to the first JSON object.

    The student is trained to emit one line of JSON followed by EOS; anything
    after the first newline or after the brace that closes the object is
    discarded. The result may still be invalid JSON; validation decides that.
    """
    s = generated.strip()
    s = s.split("\n", 1)[0].strip()
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[: i + 1]
    return s


def validate(raw, keys=None, intents=None):
    """Return the parsed frame if `raw` satisfies the schema, else None."""
    keys = keys or KEYS
    intents = intents or INTENTS
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict) or set(obj) != set(keys) or len(obj) != len(keys):
        return None
    if obj.get("intent") not in intents:
        return None
    for k in keys:
        if k == "intent":
            continue
        if obj[k] is not None and not isinstance(obj[k], str):
            return None
    return {k: obj[k] for k in keys}


def _norm(s):
    return " ".join(s.lower().split())


def salvage(raw, text, keys=None, intents=None):
    """Recover a frame from a malformed model output, or return None.

    Used only when strict parsing fails (e.g. the model loops or repeats a key).
    Every value comes from the model's own text: the first "intent" that is one of
    the allowed intents, and for each slot the first `"slot": null` or
    `"slot": "value"`; a slot value is kept only if it occurs in the command,
    otherwise the slot is null (never invented). No valid intent -> None.
    """
    import re

    keys = keys or KEYS
    intents = intents or INTENTS
    m = re.search(r'"intent"\s*:\s*"([a-z_]+)"', raw or "")
    if not m or m.group(1) not in intents:
        return None
    frame = {"intent": m.group(1)}
    command = _norm(text)
    for k in keys:
        if k == "intent":
            continue
        v = re.search(r'"%s"\s*:\s*(null|"([^"\n]*)")' % re.escape(k), raw)
        val = v.group(2) if v and v.group(2) is not None else None
        frame[k] = val if val and _norm(val) in command else None
    return {k: frame[k] for k in keys}


def parse_output(raw, text, keys=None, intents=None):
    """Strict schema validation first, then salvage. Returns (frame or None, how)."""
    frame = validate(raw, keys, intents)
    if frame is not None:
        return frame, "strict"
    frame = salvage(raw, text, keys, intents)
    return (frame, "salvaged") if frame is not None else (None, "invalid")
