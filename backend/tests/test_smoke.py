"""Smoke tests that don't require any external services."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_app_boots():
    app = create_app()
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["service"] == "faux_code"


def test_routes_registered():
    app = create_app()
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    expected = {
        "/healthz",
        "/v1/chat/completions",
        "/v1/conversations",
        "/v1/providers",
        "/v1/models",
        "/v1/settings/keys",
        "/v1/agents/runs",
        "/v1/agents/tools",
        "/v1/rag/search",
        "/v1/rag/ingest/text",
        "/v1/workspace/info",
        "/v1/workspace/tree",
    }
    missing = expected - paths
    assert not missing, f"Missing routes: {missing}"


def test_providers_list():
    app = create_app()
    client = TestClient(app)
    r = client.get("/v1/providers")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert {"ollama", "groq", "openrouter", "gemini", "cerebras", "huggingface", "vllm"} <= ids


def test_tools_registered():
    app = create_app()
    client = TestClient(app)
    r = client.get("/v1/agents/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()}
    expected = {"web_search", "web_fetch", "list_dir", "read_file", "write_file", "edit_file", "grep", "shell", "python", "rag_search"}
    assert expected <= names, f"Missing tools: {expected - names}"
