"""Authentication against mongomock. The unique-index race is enforced by mongomock here;
real MongoDB enforces the same index, but that path has not been run against Atlas."""
import asyncio
import io
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import mongomock
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pymongo.errors import DuplicateKeyError

from app import auth
from app.config import settings
from app.deps import db_provider
from app.logging_config import JsonFormatter
from app.main import app
from app.protection import Limits

SECRET = "test-signing-secret-that-is-long-enough-0123456789"
PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def fast_hasher(monkeypatch):
    """Argon2 at production cost is ~150 ms per call; use minimal cost except in the dedicated test."""
    monkeypatch.setattr(auth, "_hasher", PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


@pytest.fixture
def database(monkeypatch):
    db = mongomock.MongoClient()["auth_test"]
    monkeypatch.setattr(settings, "app_mode", "auto")
    monkeypatch.setattr(settings, "mongodb_uri", "mongodb://localhost:1")
    monkeypatch.setattr(settings, "jwt_secret", SecretStr(SECRET))
    app.dependency_overrides[db_provider] = lambda: (lambda: db)
    yield db
    app.dependency_overrides.clear()


@pytest.fixture
def client(database):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def logs():
    buf = io.StringIO()
    logger = logging.getLogger("app")
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    yield buf
    logger.removeHandler(handler)


def register(client, email="Ada@Example.com", password=PASSWORD):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def login(client, email="ada@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def forge(claims_override=None, *, secret=SECRET, algorithm="HS256", drop=()):
    now = datetime.now(timezone.utc)
    claims = {"iss": settings.jwt_issuer, "aud": settings.jwt_audience, "sub": "someone", "iat": now,
              "nbf": now, "exp": now + timedelta(minutes=5), "jti": "x"}
    claims.update(claims_override or {})
    for name in drop:
        claims.pop(name)
    return jwt.encode(claims, secret, algorithm=algorithm)


# ---- normalization and password rules -------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("  Ada@Example.COM ", "ada@example.com"), ("a.b+tag@sub.example.org", "a.b+tag@sub.example.org"),
    ("no-at-sign", None), ("two@@example.com", None), ("a b@example.com", None), ("a@localhost", None),
    ("\u00fcn\u00ef@example.com", None), ("user@ex\u0430mple.com", None),  # Cyrillic a
    ("\u212a@example.com", None),  # Kelvin sign: str.lower() would turn it into ASCII 'k'
    ("x" * 65 + "@example.com", None), ("a@" + "b" * 250 + ".com", None),
])
def test_email_normalization_rule(raw, expected):
    assert auth.normalize_email(raw) == expected


def test_password_bounds_count_characters_and_do_not_truncate(client):
    assert register(client, password="a" * 11).status_code == 422
    assert register(client, "min@example.com", "a" * 12).status_code == 201
    assert register(client, "max@example.com", "é" * 128).status_code == 201  # 256 bytes, 128 characters
    assert register(client, "over@example.com", "a" * 129).status_code == 422
    long_pw = "p" * 127 + "x"
    register(client, "long@example.com", long_pw)
    assert login(client, "long@example.com", long_pw).status_code == 200
    assert login(client, "long@example.com", "p" * 127 + "y").status_code == 401  # last char matters


def test_validation_errors_do_not_echo_password_or_email(client):
    resp = register(client, email="not an email", password="short")
    assert resp.status_code == 422
    assert "short" not in resp.text and "not an email" not in resp.text
    assert {tuple(d["loc"]) for d in resp.json()["error"]["details"]} == {("body", "email"), ("body", "password")}


def test_dummy_hash_matches_the_production_parameters():
    assert not PasswordHasher().check_needs_rehash(auth.DUMMY_HASH)
    assert not auth.verify_password(auth.DUMMY_HASH, PASSWORD)


def test_production_hasher_is_argon2id_with_default_parameters(monkeypatch):
    monkeypatch.setattr(auth, "_hasher", PasswordHasher())
    hashed = auth.hash_password(PASSWORD)
    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=4$") and PASSWORD not in hashed
    assert auth.verify_password(hashed, PASSWORD) and not auth.verify_password(hashed, PASSWORD + "!")
    assert not auth.verify_password("not-a-hash", PASSWORD)


# ---- registration ---------------------------------------------------------------------------------

def test_register_returns_public_user_and_stores_normalized_email_and_hash(client, database):
    resp = register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {"id", "email", "created_at"} and body["email"] == "ada@example.com"
    stored = database["users"].find_one({"_id": body["id"]})
    assert stored["email"] == "ada@example.com" and stored["password_hash"].startswith("$argon2id$")
    assert "password" not in resp.text and "argon2" not in resp.text


def test_duplicate_email_is_rejected_whatever_the_casing_or_spacing(client, database):
    assert register(client).status_code == 201
    dup = register(client, email="  ADA@example.COM ")
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "email_taken"
    assert database["users"].count_documents({}) == 1
    assert any(i.get("unique") for i in database["users"].index_information().values())


def test_concurrent_registration_of_one_email_creates_one_account(database):
    # this test is about the unique index, so lift the per-IP registration limit above the 12 requests
    app.state.limits = Limits.from_settings(settings.model_copy(update={"rate_register_ip_per_hour": 1000}))
    async def run():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            return await asyncio.gather(*[
                c.post("/api/auth/register", json={"email": "race@example.com", "password": PASSWORD})
                for _ in range(12)])

    codes = sorted(r.status_code for r in asyncio.run(run()))
    assert codes == [201] + [409] * 11
    assert database["users"].count_documents({"email": "race@example.com"}) == 1


def test_duplicate_key_error_from_the_database_maps_to_409():
    class Users:
        def create_index(self, *a, **k):
            pass

        def insert_one(self, doc):
            raise DuplicateKeyError("E11000 duplicate key error collection: x.users index: email_unique")

    with pytest.raises(auth.EmailTaken):
        auth.create_user({"users": Users()}, "a@example.com", PASSWORD)


# ---- login ----------------------------------------------------------------------------------------

def test_login_returns_a_short_lived_bearer_token(client):
    register(client)
    resp = login(client, email=" ADA@example.com ")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == settings.access_token_ttl_minutes * 60
    claims = jwt.decode(body["access_token"], SECRET, algorithms=["HS256"], audience=settings.jwt_audience)
    assert claims["iss"] == settings.jwt_issuer and claims["exp"] - claims["iat"] == body["expires_in"]


@pytest.mark.parametrize("email,password", [("nobody@example.com", PASSWORD), ("ada@example.com", "wrong-password-123"),
                                            ("not-an-email", PASSWORD), ("ünï@example.com", PASSWORD)])
def test_login_failures_are_indistinguishable(client, email, password):
    register(client)
    resp = login(client, email=email, password=password)
    assert resp.status_code == 401
    err = resp.json()["error"]
    assert (err["code"], err["message"]) == ("invalid_credentials", "Invalid email or password.")


def test_every_failed_login_path_costs_one_password_verification(client, monkeypatch):
    register(client)
    calls = []
    original = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda stored, pw: calls.append(stored) or original(stored, pw))
    for email, pw in [("ada@example.com", "wrong-password-123"), ("nobody@example.com", PASSWORD), ("bad", PASSWORD)]:
        calls.clear()
        assert login(client, email, pw).status_code == 401
        assert len(calls) == 1 and calls[0].startswith("$argon2id$")


# ---- tokens and the current-user dependency -------------------------------------------------------

def test_me_returns_the_authenticated_user(client):
    user_id = register(client).json()["id"]
    token = login(client).json()["access_token"]
    resp = client.get("/api/auth/me", headers=bearer(token))
    assert resp.status_code == 200 and resp.json()["id"] == user_id and "password_hash" not in resp.text


def test_missing_credentials_get_a_bearer_challenge(client):
    resp = client.get("/api/auth/me", headers={"X-Request-ID": "client-req-0200"})
    assert resp.status_code == 401 and resp.headers["www-authenticate"] == "Bearer"
    err = resp.json()["error"]
    assert err["code"] == "not_authenticated" and err["request_id"] == "client-req-0200"
    assert client.get("/api/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401


def user_token(client, **kw):
    user_id = register(client).json()["id"]
    return user_id, forge({"sub": user_id, **kw.get("claims", {})}, **{k: v for k, v in kw.items() if k != "claims"})


@pytest.mark.parametrize("make", [
    lambda uid: forge({"sub": uid}, secret="a-different-secret-that-is-also-long-enough-123"),
    lambda uid: forge({"sub": uid}, algorithm="HS384"),
    lambda uid: forge({"sub": uid, "iss": "someone-else"}),
    lambda uid: forge({"sub": uid, "aud": "another-api"}),
    lambda uid: forge({"sub": uid, "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}),
    lambda uid: forge({"sub": uid, "nbf": datetime.now(timezone.utc) + timedelta(minutes=5)}),
    lambda uid: forge({"sub": uid}, drop=("exp",)),
    lambda uid: forge({"sub": uid}, drop=("jti",)),
    lambda uid: forge(drop=("sub",)),
    lambda uid: forge({"sub": 12345}),
    lambda uid: jwt.encode({"sub": uid}, key=None, algorithm="none"),
    lambda uid: "not.a.token",
], ids=["wrong-secret", "wrong-alg", "wrong-issuer", "wrong-audience", "expired", "not-yet-valid", "no-exp",
        "no-jti", "no-sub", "non-string-sub", "alg-none", "garbage"])
def test_invalid_tokens_are_rejected_uniformly(client, make):
    user_id = register(client).json()["id"]
    resp = client.get("/api/auth/me", headers=bearer(make(user_id)))
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    assert resp.json()["error"]["code"] == "invalid_token"


def test_tampered_payload_fails_signature_check(client):
    register(client)
    other = register(client, "grace@example.com").json()["id"]
    token = login(client).json()["access_token"]
    header, _, signature = token.split(".")
    forged_payload = token.split(".")[1]
    forged = jwt.encode({"sub": other}, "x" * 40, algorithm="HS256").split(".")[1]
    assert forged != forged_payload
    assert client.get("/api/auth/me", headers=bearer(f"{header}.{forged}.{signature}")).status_code == 401


def test_expired_token_from_issue_token_is_rejected(client):
    user_id = register(client).json()["id"]
    old = auth.issue_token(user_id, now=datetime.now(timezone.utc) - timedelta(minutes=settings.access_token_ttl_minutes + 1))
    assert client.get("/api/auth/me", headers=bearer(old.access_token)).status_code == 401
    fresh = auth.issue_token(user_id)
    assert client.get("/api/auth/me", headers=bearer(fresh.access_token)).status_code == 200


def test_token_for_a_deleted_user_is_rejected(client, database):
    register(client)
    token = login(client).json()["access_token"]
    database["users"].delete_many({})
    resp = client.get("/api/auth/me", headers=bearer(token))
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "invalid_token"


# ---- availability, health and logging -------------------------------------------------------------

def test_auth_routes_report_unavailable_in_demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "app_mode", "demo")
    client = TestClient(app, raise_server_exceptions=False)
    for resp in (client.post("/api/auth/register", json={}), client.post("/api/auth/login", json={}),
                 client.get("/api/auth/me")):
        assert resp.status_code == 503 and resp.json()["error"]["code"] == "auth_unavailable"
        assert "demo mode" in resp.json()["error"]["message"]


def test_auth_routes_report_a_missing_signing_key(database, monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", SecretStr(""))
    resp = TestClient(app, raise_server_exceptions=False).post("/api/auth/login", json={"email": "a@b.co", "password": "x"})
    assert resp.status_code == 503 and "JWT_SECRET" in resp.json()["error"]["message"]
    assert "MONGODB_URI" not in resp.json()["error"]["message"]


def test_health_reports_auth_state(database, monkeypatch):
    monkeypatch.setattr("app.health.database_state", lambda: {"state": "connected"})
    assert TestClient(app).get("/health").json()["auth"] == "enabled"
    monkeypatch.setattr(settings, "jwt_secret", SecretStr(""))
    assert TestClient(app).get("/health").json()["auth"] == "unavailable"


def test_credentials_hashes_and_tokens_never_reach_the_logs(client, logs):
    register(client)
    token = login(client).json()["access_token"]
    login(client, password="wrong-password-123")
    register(client, password="short")
    client.get("/api/auth/me", headers=bearer(token))
    client.get("/api/auth/me", headers=bearer(token + "tampered"))
    text = logs.getvalue()
    assert {"user_registered", "login_succeeded", "login_failed", "token_rejected"} <= {
        json.loads(line)["event"] for line in text.splitlines()}
    for secret in (PASSWORD, "wrong-password-123", "short", token, "$argon2", "ada@example.com", SECRET):
        assert secret not in text
