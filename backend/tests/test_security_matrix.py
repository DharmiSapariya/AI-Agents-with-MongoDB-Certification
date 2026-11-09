"""Exercise route policy through the ASGI app with signed tokens and isolated fixtures."""
from datetime import datetime, timedelta, timezone

import pytest
from clock import Clock
from fastapi.routing import iter_route_contexts

from app import auth, graph, sessions
from app.config import settings
from app.main import app
from app.protection import Limits

# Method, registered path, request path, body, policy, success status.
ROUTES = (
    ("GET", "/", "/", None, "public", 200),
    ("GET", "/health", "/health", None, "public", 200),
    ("GET", "/docs", "/docs", None, "public", 200),
    ("GET", "/docs/oauth2-redirect", "/docs/oauth2-redirect", None, "public", 200),
    ("GET", "/redoc", "/redoc", None, "public", 200),
    ("GET", "/openapi.json", "/openapi.json", None, "public", 200),
    ("POST", "/api/auth/register", "/api/auth/register",
     {"email": "new@example.com", "password": "a long enough passphrase"}, "public", 201),
    ("POST", "/api/auth/login", "/api/auth/login",
     {"email": "a@example.com", "password": "a long enough passphrase"}, "public", 200),
    ("GET", "/api/auth/me", "/api/auth/me", None, "auth", 200),
    ("GET", "/api/mentor/teach/{concept}", "/api/mentor/teach/agent", None, "public", 200),
    ("GET", "/api/mentor/quiz", "/api/mentor/quiz", None, "public", 200),
    ("POST", "/api/mentor/quiz", "/api/mentor/quiz", {"answers": {}}, "mode-dependent", 200),
    ("POST", "/api/chat", "/api/chat", {"message": "hello", "session_id": "s_alice"}, "owner", 200),
    ("GET", "/api/sessions", "/api/sessions", None, "owner-list", 200),
    ("GET", "/api/sessions/{session_id}", "/api/sessions/s_alice", None, "owner", 200),
    ("GET", "/api/executions", "/api/executions", None, "owner-list", 200),
    ("GET", "/api/executions/{execution_id}", "/api/executions/run-alice", None, "owner", 200),
    ("GET", "/api/mentor/explain/{execution_id}", "/api/mentor/explain/run-alice", None, "owner", 200),
    ("GET", "/api/db/collections", "/api/db/collections", None, "owner-list", 200),
    ("GET", "/api/db/sample/{name}", "/api/db/sample/agent_execution_events", None, "owner-list", 200),
)


def test_each_registered_http_method_has_an_explicit_policy():
    registered = {(method, route.path) for route in iter_route_contexts(app.routes) for method in route.methods}
    # Starlette adds HEAD to the framework docs routes, which share their GET policy.
    framework_paths = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
    expected = {(method, path) for method, path, *_ in ROUTES}
    expected |= {("HEAD", path) for path in framework_paths}
    assert registered == expected


@pytest.fixture
def seeded(two_users, monkeypatch):
    client, database, alice, bob = two_users
    calls = []

    def run(thread_id, message, user_id):
        calls.append((thread_id, message, user_id))
        return {"answer": "ok"}

    monkeypatch.setattr(graph, "run", run)
    monkeypatch.setattr("app.health.database_state", lambda: {"state": "connected"})
    now = datetime.now(timezone.utc)
    for label, user in (("alice", alice), ("bob", bob), ("legacy", None)):
        owner = {"user_id": user["id"]} if user else {}
        database.sessions.insert_one({
            "_id": f"s_{label}", "created_at": now, "updated_at": now, "turns": 0, **owner,
        })
        database.agent_execution_events.insert_one({
            "execution_id": f"run-{label}", "type": "execution_end", "seq": 1,
            "ts": now, "data": {"marker": f"private-{label}"}, **owner,
        })
    return client, database, alice, bob, calls


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error["request_id"] == response.headers["x-request-id"]
    return error["message"]


@pytest.mark.parametrize("method,registered,path,body,policy,success", ROUTES,
                         ids=[f"{method} {path}" for method, path, *_ in ROUTES])
def test_route_policy(seeded, method, registered, path, body, policy, success):
    client, database, alice, bob, calls = seeded
    if policy == "public":
        response = client.request(method, path, json=body)
        assert response.status_code == success, response.text
        return

    expired = auth.issue_token(alice["id"], now=datetime.now(timezone.utc) - timedelta(days=1))
    assert_error(client.request(method, path, json=body), 401, "not_authenticated")
    for token in ("invalid", expired.access_token):
        denied = client.request(method, path, json=body, headers={"Authorization": f"Bearer {token}"})
        assert_error(denied, 401, "invalid_token")

    if policy == "owner":
        before = {name: list(database[name].find()) for name in ("sessions", "agent_execution_events")}
        denied = client.request(method, path, json=body, headers=bob["headers"])
        missing_path = path.replace("s_alice", "s_missing").replace("run-alice", "run-missing")
        missing_body = {**body, "session_id": "s_missing"} if body else None
        missing = client.request(method, missing_path, json=missing_body, headers=bob["headers"])
        code = "session_not_found" if path.startswith("/api/session") or method == "POST" else "execution_not_found"
        assert assert_error(denied, 404, code) == assert_error(missing, 404, code)
        legacy_path = path.replace("s_alice", "s_legacy").replace("run-alice", "run-legacy")
        legacy_body = {**body, "session_id": "s_legacy"} if body else None
        legacy = client.request(method, legacy_path, json=legacy_body, headers=alice["headers"])
        assert_error(legacy, 404, code)
        assert calls == []
        assert before == {name: list(database[name].find()) for name in before}

    response = client.request(method, path, json=body, headers=alice["headers"])
    assert response.status_code == success, response.text
    assert not any(value in response.text for value in ("s_bob", "s_legacy", "private-bob", "private-legacy"))
    if method == "POST" and path == "/api/chat":
        assert calls == [("s_alice", "hello", alice["id"])]


@pytest.mark.parametrize("path", ["/api/executions", "/api/db/sample/agent_execution_events"])
def test_execution_pagination_filters_before_slicing(seeded, path):
    client, database, alice, bob, _ = seeded
    for user, label in ((alice, "alice"), (bob, "bob")):
        first = client.get(path, params={"limit": 1, "skip": 0}, headers=user["headers"])
        assert first.status_code == 200
        assert [row["execution_id"] for row in first.json()] == [f"run-{label}"]
        second = client.get(path, params={"limit": 1, "skip": 1}, headers=user["headers"])
        assert second.status_code == 200
        assert second.json() == []


def test_chat_rejection_precedence(seeded, monkeypatch):
    client, _, alice, bob, calls = seeded
    clock = Clock()
    limits = settings.model_copy(update={"rate_chat_ip_per_min": 4, "rate_chat_user_per_min": 1})
    app.state.limits = Limits.from_settings(limits, clock)
    lookups = []
    original = sessions.get_owned

    def lookup(*args):
        lookups.append(args[2])
        return original(*args)

    monkeypatch.setattr(sessions, "get_owned", lookup)
    assert_error(client.post("/api/chat", content=b"x" * 32769), 413, "payload_too_large")
    assert_error(client.post("/api/chat", json={"message": "hello"}), 401, "not_authenticated")
    payload = {"message": "hello", "session_id": "s_bob"}
    assert_error(client.post("/api/chat", json=payload, headers=alice["headers"]), 404, "session_not_found")
    limited = client.post("/api/chat", json=payload, headers=alice["headers"])
    assert_error(limited, 429, "rate_limited")
    assert limited.headers["retry-after"] == "60"
    # The shared IP bucket is now empty. It wins even over the size check.
    assert_error(client.post("/api/chat", content=b"x" * 32769, headers=bob["headers"]), 429, "rate_limited")
    assert lookups == ["s_bob"]
    assert calls == []
