"""Connection lifecycle and health. Uses fake clients and mongomock; no real MongoDB is contacted."""
from types import SimpleNamespace

import mongomock
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app import health, mongo
from app.config import settings
from app.main import app

URI = "mongodb://user:hunter2@localhost:1/?directConnection=true"


class FakeClient:
    def __init__(self, error: Exception | None = None):
        self.closed = 0
        self.pings = 0
        self.admin = SimpleNamespace(command=self._command)
        self._error = error

    def _command(self, name):
        self.pings += 1
        if self._error:
            raise self._error
        return {"ok": 1}

    def close(self):
        self.closed += 1


@pytest.fixture(autouse=True)
def isolated_client():
    previous = mongo.set_client(None)
    yield
    mongo.set_client(previous)


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(settings, "mongodb_uri", URI)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-123456789")
    monkeypatch.setattr(settings, "voyage_api_key", "pa-test-123456789")
    monkeypatch.setattr(settings, "app_mode", "auto")


def test_explicit_demo_mode_never_touches_the_database(monkeypatch):
    monkeypatch.setattr(settings, "app_mode", "demo")
    fake = FakeClient()
    mongo.set_client(fake)
    body, status = health.report()
    assert status == 200 and body["mongodb"] == "demo" and body["mode"] == "demo" and fake.pings == 0


def test_not_configured_is_reported_in_auto_mode(monkeypatch):
    monkeypatch.setattr(settings, "app_mode", "auto")
    monkeypatch.setattr(settings, "mongodb_uri", "")
    body, status = health.report()
    assert status == 200 and body["mongodb"] == "not_configured"


def test_live_with_unreachable_database_is_503_and_leaks_nothing(live):
    mongo.set_client(FakeClient(ServerSelectionTimeoutError(f"cannot reach {URI}")))
    resp = TestClient(app).get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded" and body["mongodb"] == "unreachable"
    assert body["database"] == {"state": "unreachable"}  # the exception type is logged, not published
    assert "hunter2" not in resp.text and "localhost" not in resp.text


def test_live_with_working_database_reports_connected(live):
    fake = FakeClient()
    mongo.set_client(fake)
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200 and resp.json()["mongodb"] == "connected" and fake.pings == 1


def test_partial_credentials_still_report_the_real_database_state(monkeypatch):
    monkeypatch.setattr(settings, "app_mode", "auto")
    monkeypatch.setattr(settings, "mongodb_uri", URI)
    monkeypatch.setattr(settings, "openai_api_key", "")
    mongo.set_client(FakeClient(ServerSelectionTimeoutError("down")))
    body, status = health.report()
    assert status == 200 and body["mode"] == "demo" and body["mongodb"] == "unreachable"
    assert "missing_credentials" not in body and "OPENAI_API_KEY" not in str(body)


def test_connect_configures_timeouts_and_reuses_one_client(monkeypatch):
    monkeypatch.setattr(settings, "mongodb_uri", URI)
    first = mongo.connect()
    try:
        assert mongo.connect() is first and mongo.client() is first
        assert first.options.server_selection_timeout == settings.mongo_timeout_ms / 1000
        assert first.options.pool_options.connect_timeout == settings.mongo_timeout_ms / 1000
        assert first.options.pool_options.socket_timeout == settings.mongo_socket_timeout_ms / 1000
        assert first.options.pool_options.max_pool_size == settings.mongo_max_pool_size
    finally:
        mongo.close()


def test_connect_without_uri_fails_clearly(monkeypatch):
    monkeypatch.setattr(settings, "mongodb_uri", "")
    with pytest.raises(mongo.DatabaseNotConfigured, match="MONGODB_URI"):
        mongo.connect()


def test_close_closes_the_client_once_and_is_safe_to_repeat():
    fake = FakeClient()
    mongo.set_client(fake)
    mongo.close()
    mongo.close()
    assert fake.closed == 1


def test_set_client_injects_a_database_for_callers():
    mock = mongomock.MongoClient()
    mongo.set_client(mock)
    assert mongo.db().name == settings.db_name and mongo.client() is mock


def test_lifespan_connects_in_live_mode_and_closes_on_shutdown(live):
    fake = FakeClient()
    mongo.set_client(fake)
    with TestClient(app):
        assert fake.pings == 1 and fake.closed == 0
    assert fake.closed == 1


def test_app_starts_even_if_database_is_down_and_still_closes(live):
    fake = FakeClient(ServerSelectionTimeoutError("down"))
    mongo.set_client(fake)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 503
    assert fake.closed == 1


def test_demo_mode_lifespan_creates_no_client(monkeypatch):
    monkeypatch.setattr(settings, "app_mode", "demo")
    with TestClient(app):
        assert mongo._client is None


def test_read_routes_use_the_injected_database_and_only_return_the_callers_records(signed_in):
    database = signed_in
    database["agent_execution_events"].insert_many([
        {"type": "execution_end", "execution_id": "e1", "ts": 1, "user_id": "u1"},
        {"type": "execution_end", "execution_id": "e2", "ts": 2, "user_id": "u2"},
        {"type": "execution_end", "execution_id": "legacy", "ts": 3}])
    database["full_docs"].insert_one({"title": "T", "body": "b", "source": "t.md", "hash": "h", "chunk_count": 1})
    client = TestClient(app)
    assert client.get("/api/executions").json() == [{"type": "execution_end", "execution_id": "e1", "ts": 1, "user_id": "u1"}]
    names = {c["name"]: c for c in client.get("/api/db/collections").json()}
    assert names["full_docs"]["scope"] == "shared" and names["full_docs"]["count"] == 1
    assert names["agent_execution_events"] == {"name": "agent_execution_events", "scope": "owned", "count": 1}
    sample = client.get("/api/db/sample/full_docs").json()[0]
    assert sample["title"] == "T" and "body" not in sample
