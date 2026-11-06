import importlib

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("transformers")
from fastapi.testclient import TestClient  # noqa: E402


def make_client(monkeypatch, fault="0", output='{"intent": "weather_query", "date": null, "time": null, "place": "london"}'):
    for k, v in {"MODEL_URI": "s3://models/v1", "MODEL_VERSION": "v1", "S3_ENDPOINT": "http://x",
                 "MAX_NEW_TOKENS": "64", "FAULT_INJECT": fault, "POD_NAME": "pod-a",
                 "SCHEMA_PATH": "data/schema.json"}.items():
        monkeypatch.setenv(k, v)
    import app
    app = importlib.reload(app)
    app.state["model"] = object()          # pretend the model is loaded
    monkeypatch.setattr(app, "generate", lambda text: " " + output + "\n")
    return app, TestClient(app.app)


def test_parse_returns_frame_and_headers(monkeypatch):
    _, c = make_client(monkeypatch)
    r = c.post("/parse", json={"text": "weather in london"})
    assert r.status_code == 200
    assert r.json() == {"intent": "weather_query", "date": None, "time": None, "place": "london"}
    assert r.headers["X-Model-Version"] == "v1" and r.headers["X-Served-By"] == "pod-a"


def test_fault_inject_gives_500(monkeypatch):
    _, c = make_client(monkeypatch, fault="1")
    r = c.post("/parse", json={"text": "weather in london"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}


def test_invalid_model_output_never_200(monkeypatch):
    _, c = make_client(monkeypatch, output='{"intent": "play_music", "date": nu')
    r = c.post("/parse", json={"text": "weather in london"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}


def test_readyz_503_until_loaded(monkeypatch):
    app, c = make_client(monkeypatch)
    assert c.get("/healthz").status_code == 200
    app.state["model"] = None
    assert c.get("/readyz").status_code == 503
    app.state["model"] = object()
    assert c.get("/readyz").status_code == 200


def test_malformed_but_salvageable_output_returns_clean_json(monkeypatch):
    _, c = make_client(monkeypatch, output='{"intent": "weather_query", "date": null, "time": null, "place": "london house house')
    r = c.post("/parse", json={"text": "weather in london"})
    assert r.status_code == 200
    assert r.json() == {"intent": "weather_query", "date": None, "time": None, "place": None}
