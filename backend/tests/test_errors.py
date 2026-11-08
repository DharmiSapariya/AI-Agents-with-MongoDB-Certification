import io
import json
import logging

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from langgraph.errors import GraphRecursionError
from pymongo import errors as mongo_errors
from voyageai.error import VoyageError

from app import graph
from app.config import settings
from app.errors import ApiError, classify
from app.logging_config import JsonFormatter
from app.main import app

URI = "mongodb+srv://user:hunter2@cluster.example.net/db"
REQUEST = httpx.Request("POST", "https://api.example.test/v1")


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def live(monkeypatch, signed_in):
    monkeypatch.setattr(settings, "mongodb_uri", URI)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-123456789")
    monkeypatch.setattr(settings, "voyage_api_key", "pa-test-123456789")
    monkeypatch.setattr(settings, "app_mode", "auto")


@pytest.fixture
def error_log():
    buf = io.StringIO()
    logger = logging.getLogger("app.errors")
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield buf
    logger.removeHandler(handler)


CASES = [
    (mongo_errors.ServerSelectionTimeoutError(f"no servers {URI}"), 503, "database_unavailable"),
    (mongo_errors.NetworkTimeout("slow"), 504, "database_timeout"),
    (mongo_errors.OperationFailure("not authorized"), 500, "database_error"),
    (openai.APITimeoutError(request=REQUEST), 504, "llm_timeout"),
    (openai.APIConnectionError(request=REQUEST), 502, "llm_provider_error"),
    (VoyageError("bad key sk-abcdefghijklmnop"), 502, "embedding_provider_error"),
    (GraphRecursionError("Recursion limit of 12 reached"), 422, "execution_limit_exceeded"),
    (TimeoutError("deadline"), 504, "timeout"),
    (RuntimeError("anything else"), 500, "internal_error"),
]


@pytest.mark.parametrize("exc,status,code", CASES)
def test_classification(exc, status, code):
    err = classify(exc)
    assert (err.status_code, err.code) == (status, code)


def test_wrapped_failures_are_classified_by_their_cause():
    try:
        try:
            raise mongo_errors.ServerSelectionTimeoutError("down")
        except mongo_errors.PyMongoError as inner:
            raise RuntimeError("checkpoint write failed") from inner
    except RuntimeError as outer:
        assert classify(outer).code == "database_unavailable"


HANDLED = [c for c in CASES if c[2] != "internal_error"]  # unknown errors are covered by the middleware test


@pytest.mark.parametrize("exc,status,code", HANDLED)
def test_chat_failures_return_consistent_safe_errors(client, live, monkeypatch, error_log, exc, status, code):
    def failing_run(thread_id, message, user_id=None):
        raise exc

    monkeypatch.setattr(graph, "run", failing_run)
    resp = client.post("/api/chat", json={"message": "hello"},
                       headers={"X-Request-ID": "client-req-0100"})
    assert resp.status_code == status
    err = resp.json()["error"]
    assert err["code"] == code and err["request_id"] == "client-req-0100" == resp.headers["x-request-id"]
    for leaked in ("hunter2", "sk-abcdefghijklmnop", "Traceback", "RuntimeError", "cluster.example.net"):
        assert leaked not in resp.text
    logged = error_log.getvalue()
    assert "hunter2" not in logged and "sk-abcdefghijklmnop" not in logged
    if status >= 500:
        row = json.loads(logged.splitlines()[-1])
        assert row["error_category"] == code and row["exc_type"] == type(exc).__name__ and "traceback" in row


def test_unexpected_exception_is_generic_500_with_request_id(client, live, monkeypatch):
    def failing_run(thread_id, message, user_id=None):
        raise ValueError(f"unexpected {URI}")

    monkeypatch.setattr(graph, "run", failing_run)
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error" and resp.json()["error"]["request_id"]
    assert "hunter2" not in resp.text


def test_validation_errors_do_not_echo_submitted_values(client, signed_in):
    resp = client.post("/api/chat", json={"thread_id": "../x mongodb://u:hunter2@h/db", "message": "hi"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error" and err["details"][0]["loc"] == ["body", "thread_id"]
    assert "hunter2" not in resp.text
    assert all(set(d) == {"loc", "msg"} for d in err["details"])  # no echoed "input" value


def test_http_errors_use_the_same_shape(client):
    resp = client.get("/api/mentor/teach/not-a-concept")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"
    assert client.post("/health").status_code == 405
    assert client.post("/health").json()["error"]["code"] == "method_not_allowed"


def test_demo_mode_error_has_its_own_code(client, monkeypatch):
    monkeypatch.setattr(settings, "app_mode", "demo")
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "demo_mode"


def test_api_error_defaults_and_overrides():
    assert (ApiError().status_code, ApiError().code) == (500, "internal_error")
    custom = ApiError("nope", code="custom", status_code=418)
    assert (custom.status_code, custom.code, str(custom)) == (418, "custom", "nope")
