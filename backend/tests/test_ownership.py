"""Session and trace ownership (roadmap item 6) with two real accounts.

mongomock replaces MongoDB and the graph is faked, so this shows the route logic is scoped by
owner, not that Atlas behaves the same. The exhaustive cross-user matrix is roadmap item 8.
"""
import re

import pytest

from app import graph
from app.tracing import Tracer


@pytest.fixture
def env(two_users, monkeypatch):
    client, database, a, b = two_users
    calls = []

    def fake_run(thread_id, message, user_id=None):
        calls.append({"thread_id": thread_id, "message": message, "user_id": user_id})
        tracer = Tracer(database["agent_execution_events"], thread_id, "primary", message, user_id=user_id)
        tracer.finish("success", "ok")
        return {"answer": "ok", "execution_id": tracer.execution_id, "fully_recorded": True}

    monkeypatch.setattr(graph, "run", fake_run)
    return client, database, a, b, calls


def chat(client, who, message="hello", **extra):
    return client.post("/api/chat", json={"message": message, **extra}, headers=who["headers"])


def strip_request_id(resp):
    body = resp.json()
    body["error"].pop("request_id")
    return resp.status_code, body


# ---- chat and sessions ----------------------------------------------------------------------------

def test_chat_requires_a_token_and_does_not_reach_the_graph(env):
    client, database, a, b, calls = env
    resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "not_authenticated"
    assert calls == [] and database["sessions"].count_documents({}) == 0


def test_server_generates_the_session_id_and_binds_it_to_the_token_user(env):
    client, database, a, b, calls = env
    body = chat(client, a).json()
    assert re.fullmatch(r"s_[0-9a-f]{32}", body["session_id"])
    assert database["sessions"].find_one({"_id": body["session_id"]})["user_id"] == a["id"]
    assert calls == [{"thread_id": body["session_id"], "message": "hello", "user_id": a["id"]}]


def test_owner_can_resume_a_session(env):
    client, database, a, b, calls = env
    sid = chat(client, a).json()["session_id"]
    again = chat(client, a, session_id=sid)
    assert again.status_code == 200 and again.json()["session_id"] == sid
    assert [c["thread_id"] for c in calls] == [sid, sid]
    assert database["sessions"].find_one({"_id": sid})["turns"] == 2


def test_foreign_and_missing_sessions_are_indistinguishable_and_never_reach_the_graph(env):
    client, database, a, b, calls = env
    sid = chat(client, a).json()["session_id"]
    calls.clear()
    foreign = chat(client, b, session_id=sid)
    missing = chat(client, b, session_id="s_" + "0" * 32)
    assert foreign.status_code == 404 and strip_request_id(foreign) == strip_request_id(missing)
    assert foreign.json()["error"]["code"] == "session_not_found"
    assert calls == [] and database["sessions"].find_one({"_id": sid})["turns"] == 1


@pytest.mark.parametrize("extra", [{"thread_id": "anything"}, {"user_id": "someone"}])
def test_client_cannot_choose_the_thread_or_the_user(env, extra):
    client, database, a, b, calls = env
    assert chat(client, a, **extra).status_code == 422 and calls == []


def test_identity_headers_do_not_change_who_owns_the_work(env):
    client, database, a, b, calls = env
    resp = client.post("/api/chat", json={"message": "hi"}, headers={**a["headers"], "X-User-Id": b["id"]})
    assert resp.status_code == 200 and calls[0]["user_id"] == a["id"]
    assert database["sessions"].find_one({"_id": resp.json()["session_id"]})["user_id"] == a["id"]


def test_session_listing_is_scoped_ordered_and_paginated(env):
    client, database, a, b, calls = env
    ids = [chat(client, a).json()["session_id"] for _ in range(3)]
    chat(client, b)
    listed = client.get("/api/sessions", headers=a["headers"]).json()
    assert [s["id"] for s in listed] == ids[::-1]  # newest first
    assert len(client.get("/api/sessions?limit=2", headers=a["headers"]).json()) == 2
    assert [s["id"] for s in client.get("/api/sessions?limit=2&skip=2", headers=a["headers"]).json()] == [ids[0]]
    assert len(client.get("/api/sessions", headers=b["headers"]).json()) == 1
    assert client.get("/api/sessions?limit=51", headers=a["headers"]).status_code == 422
    assert client.get("/api/sessions").status_code == 401


def test_session_detail_hides_other_users_sessions(env):
    client, database, a, b, calls = env
    sid = chat(client, a).json()["session_id"]
    assert client.get(f"/api/sessions/{sid}", headers=a["headers"]).json()["turns"] == 1
    foreign = client.get(f"/api/sessions/{sid}", headers=b["headers"])
    missing = client.get("/api/sessions/s_" + "1" * 32, headers=b["headers"])
    assert strip_request_id(foreign) == strip_request_id(missing) and foreign.status_code == 404
    assert client.get("/api/sessions/bad id!", headers=a["headers"]).status_code in (400, 404)


# ---- executions, traces and the Mentor ------------------------------------------------------------

def test_executions_are_scoped_to_their_owner(env):
    client, database, a, b, calls = env
    execution = chat(client, a).json()["execution_id"]
    mine = client.get("/api/executions", headers=a["headers"]).json()
    assert [e["execution_id"] for e in mine] == [execution] and mine[0]["user_id"] == a["id"]
    assert client.get("/api/executions", headers=b["headers"]).json() == []
    events = client.get(f"/api/executions/{execution}", headers=a["headers"]).json()
    assert [e["seq"] for e in events] == [1, 2] and {e["user_id"] for e in events} == {a["id"]}
    foreign = client.get(f"/api/executions/{execution}", headers=b["headers"])
    unknown = client.get("/api/executions/" + "f" * 32, headers=b["headers"])
    assert foreign.status_code == 404 and strip_request_id(foreign) == strip_request_id(unknown)
    assert client.get("/api/executions").status_code == 401


def test_mentor_explain_follows_the_same_ownership_rule(env):
    client, database, a, b, calls = env
    execution = chat(client, a).json()["execution_id"]
    assert client.get(f"/api/mentor/explain/{execution}", headers=a["headers"]).status_code == 200
    resp = client.get(f"/api/mentor/explain/{execution}", headers=b["headers"])
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "execution_not_found"
    assert client.get(f"/api/mentor/explain/{execution}").status_code == 401


def test_legacy_records_without_an_owner_are_hidden_and_never_claimed(env):
    client, database, a, b, calls = env
    database["agent_execution_events"].insert_many([
        {"execution_id": "legacy1", "seq": 1, "type": "execution_start", "ts": 1},
        {"execution_id": "legacy1", "seq": 2, "type": "execution_end", "ts": 2}])
    database["quiz_attempts"].insert_one({"score": 3})
    for who in (a, b):
        assert client.get("/api/executions", headers=who["headers"]).json() == []
        assert client.get("/api/executions/legacy1", headers=who["headers"]).status_code == 404
        assert client.get("/api/mentor/explain/legacy1", headers=who["headers"]).status_code == 404
        assert client.get("/api/db/sample/quiz_attempts", headers=who["headers"]).json() == []
    assert database["agent_execution_events"].count_documents({"user_id": {"$exists": True}}) == 0


# ---- quiz grading ---------------------------------------------------------------------------------

def test_quiz_attempts_are_stored_for_the_token_user_only(env):
    client, database, a, b, calls = env
    resp = client.post("/api/mentor/quiz", json={"answers": {"q1": 0}}, headers=a["headers"])
    assert resp.status_code == 200
    assert database["quiz_attempts"].find_one()["user_id"] == a["id"]
    assert client.post("/api/mentor/quiz", json={"answers": {}, "user_id": b["id"]}, headers=a["headers"]).status_code == 422
    assert client.post("/api/mentor/quiz", json={"answers": {}}).status_code == 401


def test_quiz_grading_stays_anonymous_in_demo_mode(env, monkeypatch):
    client, database, a, b, calls = env
    monkeypatch.setattr("app.config.Settings.auth_enabled", property(lambda self: False))
    resp = client.post("/api/mentor/quiz", json={"answers": {"q1": 0}})
    assert resp.status_code == 200 and database["quiz_attempts"].count_documents({}) == 0


# ---- explorer -------------------------------------------------------------------------------------

def test_explorer_returns_only_the_callers_records_and_fixed_fields(env):
    client, database, a, b, calls = env
    chat(client, a)
    chat(client, a)
    chat(client, b)
    database["chunked_docs"].insert_one({"title": "T", "body": "text", "embedding": [0.1] * 4, "source": "s", "chunk_index": 0})
    names = {c["name"]: c for c in client.get("/api/db/collections", headers=a["headers"]).json()}
    assert names["sessions"]["count"] == 2 and names["agent_execution_events"]["count"] == 4
    theirs = {c["name"]: c["count"] for c in client.get("/api/db/collections", headers=b["headers"]).json()}
    assert theirs["sessions"] == 1 and theirs["agent_execution_events"] == 2
    sessions = client.get("/api/db/sample/sessions", headers=a["headers"]).json()
    assert len(sessions) == 2 and {s["user_id"] for s in sessions} == {a["id"]}
    chunk = client.get("/api/db/sample/chunked_docs", headers=a["headers"]).json()[0]
    assert set(chunk) == {"_id", "title", "source", "chunk_index"}  # no body, no embedding


@pytest.mark.parametrize("name", ["users", "checkpoints", "checkpoint_writes", "system.users", "$cmd"])
def test_explorer_refuses_collections_outside_the_allowlist(env, name):
    client, database, a, b, calls = env
    assert client.get(f"/api/db/sample/{name}", headers=a["headers"]).status_code in (403, 404)


def test_explorer_pagination_is_bounded_and_needs_a_token(env):
    client, database, a, b, calls = env
    assert client.get("/api/db/sample/sessions?limit=21", headers=a["headers"]).status_code == 422
    assert client.get("/api/db/sample/sessions?skip=1001", headers=a["headers"]).status_code == 422
    assert client.get("/api/db/sample/sessions").status_code == 401
    assert client.get("/api/db/collections").status_code == 401


# ---- public surface -------------------------------------------------------------------------------

def test_public_health_body_is_minimal(env, monkeypatch):
    client, *_ = env
    monkeypatch.setattr("app.health.database_state", lambda: {"state": "connected"})
    assert set(client.get("/health").json()) == {"status", "mode", "mongodb", "database", "auth"}
