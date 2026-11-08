import mongomock
import pytest
from fastapi.testclient import TestClient

from app import indexes
from app.config import settings
from app.main import app

client = TestClient(app)


def test_demo_mode_returns_503_for_live_endpoints(monkeypatch):
    monkeypatch.setattr(type(settings), "configured", property(lambda self: False))
    for method, path in [("get", "/api/executions"), ("get", "/api/db/collections"),
                         ("get", "/api/executions/abc")]:
        assert getattr(client, method)(path).status_code == 503
    assert client.post("/api/chat", json={"thread_id": "a", "message": "hi"}).status_code == 503


@pytest.mark.parametrize("limit", [0, -5, 101])
def test_executions_limit_is_validated(signed_in, limit):
    assert client.get(f"/api/executions?limit={limit}").status_code == 422


def test_chat_rejects_client_thread_ids_bad_session_ids_and_empty_messages(signed_in):
    assert client.post("/api/chat", json={"thread_id": "ok", "message": "hi"}).status_code == 422
    assert client.post("/api/chat", json={"session_id": "../x", "message": "hi"}).status_code == 422
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


def test_sample_endpoint_only_serves_allowlisted_collections(signed_in):
    assert client.get("/api/db/sample/checkpoints").status_code == 403


def test_mentor_quiz_hides_answers():
    body = client.get("/api/mentor/quiz").json()
    assert body and all("answer" not in q and "why" not in q for q in body)


def test_indexes_are_created_idempotently():
    database = mongomock.MongoClient()["t"]
    first = indexes.ensure_indexes(database)
    assert indexes.ensure_indexes(database) == first
    assert "execution_id_1_seq_1" in database["agent_execution_events"].index_information()
