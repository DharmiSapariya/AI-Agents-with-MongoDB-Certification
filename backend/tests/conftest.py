from datetime import datetime, timezone

import mongomock
import pytest

from app import auth
from app.config import settings
from app.deps import db_provider
from app.main import app


@pytest.fixture(autouse=True)
def fresh_limits():
    """Every test starts with empty rate-limit counters and real-clock default limits."""
    from app.logging_config import EventThrottle, set_throttle
    from app.protection import Limits

    app.state.limits = Limits.from_settings(settings)
    previous = set_throttle(EventThrottle(10))
    yield
    set_throttle(previous)


@pytest.fixture
def signed_in(monkeypatch):
    """Live mode with a fixed authenticated user ("u1") and an injected mongomock database.

    For tests of route behaviour that is not about authentication itself; test_auth.py and
    test_ownership.py use real tokens.
    """
    database = mongomock.MongoClient()["conftest"]
    user = {"_id": "u1", "email": "u1@example.com", "created_at": datetime.now(timezone.utc)}
    monkeypatch.setattr(type(settings), "configured", property(lambda self: True))
    app.dependency_overrides[auth.get_current_user] = lambda: user
    app.dependency_overrides[db_provider] = lambda: (lambda: database)
    yield database
    app.dependency_overrides.clear()


@pytest.fixture
def two_users(monkeypatch):
    """Live config with real accounts and tokens for two users; returns (client, database, a, b).

    a and b are dicts with id and Authorization headers. mongomock stands in for MongoDB and the
    Argon2 cost is minimal; the real graph is replaced by a fake that records its arguments.
    """
    from argon2 import PasswordHasher
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    monkeypatch.setattr(auth, "_hasher", PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))
    database = mongomock.MongoClient()["ownership"]
    monkeypatch.setattr(settings, "app_mode", "auto")
    monkeypatch.setattr(settings, "mongodb_uri", "mongodb://localhost:1")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-123456789")
    monkeypatch.setattr(settings, "voyage_api_key", "pa-test-123456789")
    monkeypatch.setattr(settings, "jwt_secret", SecretStr("o" * 40))
    app.dependency_overrides[db_provider] = lambda: (lambda: database)
    client = TestClient(app, raise_server_exceptions=False)

    def account(email):
        password = "a long enough passphrase"
        user_id = client.post("/api/auth/register", json={"email": email, "password": password}).json()["id"]
        token = client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]
        return {"id": user_id, "headers": {"Authorization": f"Bearer {token}"}}

    yield client, database, account("a@example.com"), account("b@example.com")
    app.dependency_overrides.clear()
