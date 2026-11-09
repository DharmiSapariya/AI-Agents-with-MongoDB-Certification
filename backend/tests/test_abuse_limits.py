"""Rate limits and size caps on the real app with two accounts. mongomock and a fake graph; no providers."""
import io
import json
import logging

import pytest
from clock import Clock
from pymongo.errors import ServerSelectionTimeoutError

from app import auth, graph, sessions
from app.config import settings
from app.logging_config import JsonFormatter
from app.main import app
from app.protection import Limits
from app.tracing import Tracer


@pytest.fixture
def env(two_users, monkeypatch):
    client, database, a, b = two_users
    spies = {"run": 0, "create": 0, "hash": 0, "verify": 0}

    def fake_run(thread_id, message, user_id=None):
        spies["run"] += 1
        tracer = Tracer(database["agent_execution_events"], thread_id, "primary", message, user_id=user_id)
        tracer.finish("success", "ok")
        return {"answer": "ok", "execution_id": tracer.execution_id, "fully_recorded": True}

    def counted(name, original):
        def wrapper(*args, **kwargs):
            spies[name] += 1
            return original(*args, **kwargs)
        return wrapper

    monkeypatch.setattr(graph, "run", fake_run)
    monkeypatch.setattr(sessions, "create", counted("create", sessions.create))
    monkeypatch.setattr(auth, "hash_password", counted("hash", auth.hash_password))
    monkeypatch.setattr(auth, "verify_password", counted("verify", auth.verify_password))
    return client, database, a, b, spies


def limit(clock=None, **overrides):
    clock = clock or Clock()
    app.state.limits = Limits.from_settings(settings.model_copy(update=overrides), clock)
    return clock


def chat(client, who=None, **body):
    return client.post("/api/chat", json={"message": "hi", **body}, headers=who["headers"] if who else {})


def without_request_id(resp):
    body = resp.json()
    body["error"].pop("request_id")
    return resp.status_code, body


# ---- IP limits happen before Argon2 --------------------------------------------------------------

def test_login_attempts_over_the_ip_budget_never_reach_argon2(env):
    client, database, a, b, spies = env
    limit(rate_login_ip_per_min=3)
    spies["verify"] = 0
    attempts = [client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-password-123"})
                for _ in range(6)]
    assert [r.status_code for r in attempts] == [401, 401, 401, 429, 429, 429]
    assert spies["verify"] == 3  # the three 429s cost no password verification


def test_throttled_login_looks_the_same_for_real_and_unknown_accounts(env):
    client, database, a, b, spies = env
    limit(rate_login_ip_per_min=1)
    known = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-password-123"})
    assert known.status_code == 401
    second = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-password-123"})
    third = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-123"})
    assert without_request_id(second) == without_request_id(third) and second.status_code == 429


def test_registration_over_the_ip_budget_creates_nothing_and_hashes_nothing(env):
    client, database, a, b, spies = env
    limit(rate_register_ip_per_hour=2)
    spies["hash"] = 0
    users_before = database["users"].count_documents({})
    codes = [client.post("/api/auth/register", json={"email": f"new{i}@example.com", "password": "a long enough passphrase"}).status_code
             for i in range(4)]
    assert codes == [201, 201, 429, 429]
    assert spies["hash"] == 2 and database["users"].count_documents({}) == users_before + 2


def test_login_and_registration_budgets_are_separate(env):
    client, database, a, b, spies = env
    limit(rate_login_ip_per_min=1, rate_register_ip_per_hour=5)
    client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-password-123"})
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"}).status_code == 429
    ok = client.post("/api/auth/register", json={"email": "fresh@example.com", "password": "a long enough passphrase"})
    assert ok.status_code == 201


# ---- per-user chat budget -------------------------------------------------------------------------

def test_user_budget_is_enforced_after_auth_and_before_any_work(env):
    client, database, a, b, spies = env
    clock = limit(rate_chat_user_per_min=2, rate_chat_ip_per_min=100)
    assert [chat(client, a).status_code for _ in range(2)] == [200, 200]
    sessions_before, runs_before = database["sessions"].count_documents({}), spies["run"]
    denied = chat(client, a)
    assert denied.status_code == 429 and denied.json()["error"]["code"] == "rate_limited"
    assert denied.headers["retry-after"] == "30" and denied.json()["error"]["request_id"] == denied.headers["x-request-id"]
    assert spies["run"] == runs_before and database["sessions"].count_documents({}) == sessions_before
    clock.advance(30)
    assert chat(client, a).status_code == 200


def test_two_users_on_one_address_have_independent_user_budgets(env):
    client, database, a, b, spies = env
    limit(rate_chat_user_per_min=1, rate_chat_ip_per_min=100)
    assert chat(client, a).status_code == 200 and chat(client, a).status_code == 429
    assert chat(client, b).status_code == 200  # same IP, own budget


def test_the_shared_ip_cap_still_applies_to_every_user_behind_it(env):
    client, database, a, b, spies = env
    limit(rate_chat_user_per_min=10, rate_chat_ip_per_min=2)
    assert chat(client, a).status_code == 200 and chat(client, b).status_code == 200
    assert chat(client, a).status_code == 429 and chat(client, b).status_code == 429


def test_headers_and_body_cannot_choose_whose_budget_is_charged(env):
    client, database, a, b, spies = env
    limit(rate_chat_user_per_min=1, rate_chat_ip_per_min=100)
    assert chat(client, a).status_code == 200
    spoofed = client.post("/api/chat", json={"message": "hi"}, headers={**a["headers"], "X-User-Id": b["id"]})
    assert spoofed.status_code == 429  # still A's budget
    assert chat(client, b).status_code == 200  # B's budget was not touched by A's spoofing
    assert chat(client, a, user_id=b["id"]).status_code == 429  # extra body field: budget check comes first


def test_throttled_callers_cannot_tell_foreign_sessions_from_missing_ones(env):
    client, database, a, b, spies = env
    limit(rate_chat_user_per_min=1, rate_chat_ip_per_min=100)
    foreign_id = chat(client, b).json()["session_id"]
    assert chat(client, a).status_code == 200
    foreign = chat(client, a, session_id=foreign_id)
    missing = chat(client, a, session_id="s_" + "0" * 32)
    assert foreign.status_code == 429 and without_request_id(foreign) == without_request_id(missing)


# ---- what counts against each budget --------------------------------------------------------------

def test_unauthenticated_chat_spends_the_ip_budget_but_not_anyones_user_budget(env):
    client, database, a, b, spies = env
    limit(rate_chat_user_per_min=1, rate_chat_ip_per_min=4)
    assert [chat(client).status_code for _ in range(3)] == [401, 401, 401]
    assert chat(client, a).status_code == 200  # user budget untouched; this was the 4th IP request
    assert chat(client, a).status_code == 429  # IP cap (4) reached; the middleware answered


def test_malformed_bodies_spend_the_user_budget(env):
    client, database, a, b, spies = env
    limit(rate_chat_user_per_min=1, rate_chat_ip_per_min=100)
    assert client.post("/api/chat", json={"message": ""}, headers=a["headers"]).status_code == 422
    assert chat(client, a).status_code == 429


def test_ownership_denials_spend_the_user_budget(env):
    client, database, a, b, spies = env
    limit(rate_chat_user_per_min=1, rate_chat_ip_per_min=100)
    assert chat(client, a, session_id="s_" + "0" * 32).status_code == 404
    assert chat(client, a).status_code == 429


def test_provider_failures_spend_the_user_budget(env, monkeypatch):
    client, database, a, b, spies = env
    limit(rate_chat_user_per_min=1, rate_chat_ip_per_min=100)

    def failing(thread_id, message, user_id=None):
        raise ServerSelectionTimeoutError("down")

    monkeypatch.setattr(graph, "run", failing)
    assert chat(client, a).status_code == 503
    assert chat(client, a).status_code == 429


def test_cheap_reads_use_their_own_ip_budget_and_leave_chat_alone(env):
    client, database, a, b, spies = env
    limit(rate_read_ip_per_min=4, rate_chat_user_per_min=1, rate_chat_ip_per_min=100)
    reads = [client.get("/api/sessions", headers=a["headers"]).status_code for _ in range(3)]
    reads.append(client.get("/api/mentor/teach/agent").status_code)
    assert reads == [200, 200, 200, 200]
    assert client.get("/api/executions", headers=a["headers"]).status_code == 429
    assert chat(client, a).status_code == 200  # the chat budgets were not drained by reads


def test_health_is_never_limited(env, monkeypatch):
    client, *_ = env
    monkeypatch.setattr("app.health.database_state", lambda: {"state": "connected"})  # no real MongoDB here
    limit(rate_read_ip_per_min=1)
    assert {client.get("/health").status_code for _ in range(50)} == {200}


# ---- body size on the real app --------------------------------------------------------------------

def test_oversized_chat_body_is_rejected_before_auth_and_before_any_work(env):
    client, database, a, b, spies = env
    resp = client.post("/api/chat", content=b'{"message": "' + b"x" * 40000 + b'"}',
                       headers={"content-type": "application/json"})
    assert resp.status_code == 413 and resp.json()["error"]["code"] == "payload_too_large"  # not 401
    assert spies["run"] == 0 and spies["create"] == 0
    big_login = client.post("/api/auth/login", content=b'{"email":"a@example.com","password":"' + b"p" * 5000 + b'"}',
                            headers={"content-type": "application/json"})
    assert big_login.status_code == 413 and spies["verify"] == 0


def test_byte_cap_and_character_limit_are_separate_checks(env):
    client, database, a, b, spies = env
    limit(rate_chat_user_per_min=100, rate_chat_ip_per_min=100)

    def post_raw(text):
        raw = json.dumps({"message": text}, ensure_ascii=False).encode()
        return client.post("/api/chat", content=raw, headers={**a["headers"], "content-type": "application/json"}), len(raw)

    ok, size = post_raw("\U0001F600" * 2000)          # 2000 characters, ~8 KB of UTF-8
    assert ok.status_code == 200 and size > 8000
    too_many_chars, _ = post_raw("\U0001F600" * 2001)  # under the byte cap, over the character limit
    assert too_many_chars.status_code == 422 and spies["run"] == 1  # rejected, never truncated
    too_many_bytes, size = post_raw("\U0001F600" * 8300)
    assert too_many_bytes.status_code == 413 and size > settings.max_body_bytes


def test_rejections_carry_cors_headers_and_request_ids_on_the_real_app(env):
    client, database, a, b, spies = env
    limit(rate_login_ip_per_min=1)
    origin = {"Origin": "http://localhost:5173"}
    client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"}, headers=origin)
    denied = client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"},
                         headers={**origin, "X-Request-ID": "client-req-0400"})
    assert denied.status_code == 429 and denied.headers["x-request-id"] == "client-req-0400"
    assert denied.json()["error"]["request_id"] == "client-req-0400"
    assert denied.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "retry-after" in denied.headers["access-control-expose-headers"].lower()


# ---- logging --------------------------------------------------------------------------------------

@pytest.fixture
def app_logs():
    buf = io.StringIO()
    logger = logging.getLogger("app")
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield buf
    logger.removeHandler(handler)


def rows(buf, event):
    return [json.loads(line) for line in buf.getvalue().splitlines() if json.loads(line)["event"] == event]


def test_expected_503_in_demo_mode_logs_without_a_traceback_and_is_throttled(env, monkeypatch, app_logs):
    client, *_ = env
    monkeypatch.setattr(settings, "app_mode", "demo")
    for _ in range(25):
        assert client.post("/api/chat", json={"message": "private words"}).status_code == 503
    lines = rows(app_logs, "request_rejected")
    assert len(lines) == 1 and lines[0]["error_category"] == "demo_mode" and lines[0]["request_id"]
    assert "traceback" not in lines[0] and lines[0]["level"] == "WARNING"
    assert "private words" not in app_logs.getvalue() and not rows(app_logs, "request_failed")


def test_unexpected_failures_still_log_a_traceback(env, monkeypatch, app_logs):
    client, database, a, b, spies = env

    def failing(thread_id, message, user_id=None):
        raise ServerSelectionTimeoutError("cannot reach mongodb+srv://u:hunter2@h.example.net/db")

    monkeypatch.setattr(graph, "run", failing)
    assert chat(client, a).status_code == 503
    failed = rows(app_logs, "request_failed")
    assert len(failed) == 1 and failed[0]["level"] == "ERROR" and "traceback" in failed[0]
    assert "hunter2" not in app_logs.getvalue()


def test_rate_limit_floods_do_not_leak_keys_or_bodies_into_logs(env, app_logs):
    client, database, a, b, spies = env
    limit(rate_login_ip_per_min=1)
    for _ in range(20):
        client.post("/api/auth/login", json={"email": "victim@example.com", "password": "do-not-log-this"})
    text = app_logs.getvalue()
    limited = [r for r in rows(app_logs, "request_rejected") if r["error_category"] == "rate_limited"]
    assert len(limited) == 1 and limited[0]["policy"] == "login"
    for secret in ("victim@example.com", "do-not-log-this", "testclient"):
        assert secret not in text


def test_disabled_limits_leave_ownership_and_normal_chat_working(env):
    client, database, a, b, spies = env
    limit(rate_limit_enabled=False, rate_chat_user_per_min=1, rate_chat_ip_per_min=1)
    sid = chat(client, a).json()["session_id"]
    assert [chat(client, a, session_id=sid).status_code for _ in range(5)] == [200] * 5
    assert chat(client, b, session_id=sid).status_code == 404
