"""ProtectionMiddleware (IP limits and body caps) on a probe app, with the same middleware order as main.py."""
import asyncio
import hashlib
import io
import json
import logging

import pytest
from asgi import call
from clock import Clock
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.errors import install_handlers
from app.limiter import RateLimiter
from app.logging_config import EventThrottle, JsonFormatter, set_throttle
from app.middleware import RequestIdMiddleware
from app.protection import Limits, ProtectionMiddleware, client_key


class Probe:
    def __init__(self, *, login=3, register=2, chat=2, read=5, body=200, auth_body=100, enabled=True, max_keys=100):
        self.clock = Clock()
        self.hits: dict[str, int] = {}

        def bucket(n, window):
            return RateLimiter(n, window, max_keys, self.clock)

        self.limits = Limits(enabled, bucket(register, 3600), bucket(login, 60), bucket(chat, 60), bucket(chat, 60),
                             bucket(read, 60), body, auth_body)
        app = FastAPI()
        app.state.limits = self.limits
        install_handlers(app)

        async def handler(name, request: Request):
            self.hits[name] = self.hits.get(name, 0) + 1
            data = await request.body()
            return {"n": len(data), "sha": hashlib.sha256(data).hexdigest()}

        def route(name):
            async def endpoint(request: Request):
                return await handler(name, request)
            return endpoint

        for name, path in [("login", "/api/auth/login"), ("register", "/api/auth/register"),
                           ("chat", "/api/chat"), ("echo", "/echo")]:
            app.add_api_route(path, route(name), methods=["POST"])
        app.add_api_route("/api/things", route("read"), methods=["GET"])
        app.add_api_route("/health", route("health"), methods=["GET"])
        app.add_middleware(ProtectionMiddleware)
        app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET", "POST"],
                           allow_headers=["*"], expose_headers=["X-Request-ID", "Retry-After"])
        app.add_middleware(RequestIdMiddleware)
        self.app = app

    def run(self, method, path, **kw):
        return asyncio.run(call(self.app, method, path, **kw))


@pytest.fixture
def probe():
    return Probe()


def login(probe, **kw):
    return probe.run("POST", "/api/auth/login", chunks=(b'{"a":1}',), **kw)


# ---- rate limits ----------------------------------------------------------------------------------

def test_requests_below_the_budget_pass_and_the_first_over_it_gets_429(probe):
    assert [login(probe).status for _ in range(3)] == [200, 200, 200]
    denied = login(probe, headers=[("X-Request-ID", "client-req-0300")])
    assert denied.status == 429 and probe.hits["login"] == 3  # the handler never ran for the 429
    body = denied.json()["error"]
    assert body["code"] == "rate_limited" and body["request_id"] == "client-req-0300" == denied.headers["x-request-id"]
    assert denied.headers["retry-after"] == "20"  # 3 per 60 s -> one token every 20 s


def test_budget_recovers_at_the_documented_boundary(probe):
    for _ in range(4):
        login(probe)
    probe.clock.advance(19.9)
    assert login(probe).status == 429
    probe.clock.advance(0.1)
    assert login(probe).status == 200


def test_registration_login_chat_and_reads_have_separate_budgets(probe):
    for _ in range(4):
        login(probe)
    assert login(probe).status == 429
    assert probe.run("POST", "/api/auth/register", chunks=(b"{}",)).status == 200
    assert probe.run("POST", "/api/chat", chunks=(b"{}",)).status == 200
    assert probe.run("GET", "/api/things").status == 200


def test_health_and_other_exempt_paths_are_never_throttled(probe):
    assert {probe.run("GET", "/health").status for _ in range(300)} == {200}
    assert {probe.run("POST", "/echo", chunks=(b"x",)).status for _ in range(50)} == {200}


def test_different_client_addresses_have_independent_budgets(probe):
    for _ in range(4):
        login(probe, client=("198.51.100.1", 1))
    assert login(probe, client=("198.51.100.1", 2)).status == 429  # source port is not part of the key
    assert login(probe, client=("198.51.100.2", 1)).status == 200


@pytest.mark.parametrize("header", ["X-Forwarded-For", "Forwarded", "X-Real-IP", "X-Client-IP", "CF-Connecting-IP"])
def test_forwarding_headers_cannot_rotate_or_redirect_a_budget(probe, header):
    addr = ("198.51.100.1", 1)
    results = [login(probe, client=addr, headers=[(header, f"for=10.0.0.{i}" if header == "Forwarded" else f"10.0.0.{i}")])
               for i in range(6)]
    assert [r.status for r in results] == [200, 200, 200, 429, 429, 429]
    # claiming to be the exhausted address does not charge (or block) the real owner of that address
    other = login(probe, client=("198.51.100.99", 1), headers=[(header, "198.51.100.1")])
    assert other.status == 200


def test_missing_client_address_shares_one_bucket_and_does_not_crash(probe):
    statuses = [login(probe, client=None).status for _ in range(5)]
    assert statuses == [200, 200, 200, 429, 429]
    assert login(probe, client=("198.51.100.1", 1)).status == 200  # real peers are unaffected


def test_client_key_groups_ipv6_by_64_and_unmaps_ipv4():
    key = lambda host: client_key({"client": (host, 1)})  # noqa: E731
    assert key("2001:db8:1:2::1") == key("2001:db8:1:2:ffff:ffff:ffff:ffff") == "2001:db8:1:2::/64"
    assert key("2001:db8:1:3::1") != key("2001:db8:1:2::1")
    assert key("::ffff:192.0.2.7") == key("192.0.2.7") == "192.0.2.7"
    assert key("testclient") == "testclient" and client_key({}) == "unknown" and client_key({"client": None}) == "unknown"


def test_cors_preflight_is_not_counted_and_rejections_carry_cors_headers(probe):
    preflight = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
    for _ in range(10):
        assert probe.run("OPTIONS", "/api/auth/login", headers=list(preflight.items()), content_length=None).status == 200
    for _ in range(3):
        login(probe)
    denied = login(probe, headers=[("Origin", "http://localhost:5173")])
    assert denied.status == 429
    assert denied.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "retry-after" in denied.headers["access-control-expose-headers"].lower()


def test_disabled_limits_never_return_429_but_body_caps_still_apply():
    probe = Probe(login=1, enabled=False)
    assert {login(probe).status for _ in range(20)} == {200}
    assert probe.run("POST", "/api/auth/login", chunks=(b"x" * 101,)).status == 413


def test_at_key_capacity_new_clients_get_429_and_existing_budgets_survive():
    probe = Probe(login=1, max_keys=2)
    assert login(probe, client=("198.51.100.1", 1)).status == 200
    assert login(probe, client=("198.51.100.2", 1)).status == 200
    refused = login(probe, client=("198.51.100.3", 1))
    assert refused.status == 429 and int(refused.headers["retry-after"]) >= 1
    assert login(probe, client=("198.51.100.1", 1)).status == 429  # still exhausted, not erased
    probe.clock.advance(60)
    assert login(probe, client=("198.51.100.3", 1)).status == 200


# ---- body caps ------------------------------------------------------------------------------------

def test_declared_oversize_is_rejected_without_reading_the_body(probe):
    res = probe.run("POST", "/api/chat", chunks=(b"x" * 10,), content_length=201)
    assert res.status == 413 and res.receive_calls == 0 and "chat" not in probe.hits


def test_body_exactly_at_the_cap_reaches_the_handler_intact_and_one_byte_more_does_not(probe):
    payload = bytes(range(200))
    ok = probe.run("POST", "/api/chat", chunks=(payload,))
    assert ok.status == 200 and ok.json() == {"n": 200, "sha": hashlib.sha256(payload).hexdigest()}
    assert probe.run("POST", "/api/chat", chunks=(payload + b"!",)).status == 413
    assert probe.hits["chat"] == 1


def test_chunked_bodies_without_content_length_are_counted_as_they_arrive(probe):
    over = probe.run("POST", "/echo", chunks=(b"a" * 100, b"b" * 100, b"c"), content_length=None,
                     headers=[("Transfer-Encoding", "chunked")])
    assert over.status == 413 and probe.hits.get("echo") is None
    parts = (b"a" * 50, b"b" * 50, b"c" * 50, b"d" * 50)
    ok = probe.run("POST", "/echo", chunks=parts, content_length=None, headers=[("Transfer-Encoding", "chunked")])
    assert ok.status == 200 and ok.json()["sha"] == hashlib.sha256(b"".join(parts)).hexdigest()


def test_understated_content_length_does_not_bypass_the_cap(probe):
    res = probe.run("POST", "/echo", chunks=(b"x" * 500,), content_length=10)
    assert res.status == 413 and probe.hits.get("echo") is None


def test_client_disconnect_during_the_body_is_handled_quietly(probe):
    res = probe.run("POST", "/api/chat", chunks=(b"abc", b"def", b"ghi"), disconnect_after=1)
    assert res.status is None and res.body == b"" and "chat" not in probe.hits


def test_auth_routes_have_a_smaller_cap_than_the_rest(probe):
    body = (b"x" * 150,)
    assert probe.run("POST", "/api/auth/login", chunks=body).status == 413
    assert probe.run("POST", "/api/auth/register", chunks=body).status == 413
    assert probe.run("POST", "/api/chat", chunks=body).status == 200


def test_413_uses_the_error_envelope_and_does_not_echo_the_payload(probe):
    res = probe.run("POST", "/api/chat", chunks=(b"secret-payload-" * 30,), headers=[("X-Request-ID", "client-req-0301")])
    err = res.json()["error"]
    assert res.status == 413 and err["code"] == "payload_too_large" and err["request_id"] == "client-req-0301"
    assert res.headers["x-request-id"] == "client-req-0301" and res.headers["connection"] == "close"
    assert "secret-payload" not in res.body.decode() and "200 byte" in err["message"]


def test_rejected_requests_still_spend_the_ip_budget(probe):
    for _ in range(2):
        assert probe.run("POST", "/api/chat", chunks=(b"x" * 500,)).status == 413
    assert probe.run("POST", "/api/chat", chunks=(b"x",)).status == 429  # chat budget (2) used by the 413s


# ---- logging --------------------------------------------------------------------------------------

def test_a_flood_of_rejections_logs_once_per_interval_without_addresses_or_payloads(probe):
    buf = io.StringIO()
    logger = logging.getLogger("app.protection")
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    clock = Clock()
    previous = set_throttle(EventThrottle(10, clock))
    try:
        for _ in range(3):
            login(probe, client=("198.51.100.77", 1))
        for _ in range(50):
            login(probe, client=("198.51.100.77", 1), headers=[("X-Request-ID", "client-req-0302")])
        lines = [json.loads(line) for line in buf.getvalue().splitlines()]
        assert len(lines) == 1 and lines[0]["error_category"] == "rate_limited" and lines[0]["policy"] == "login"
        clock.advance(10)
        login(probe, client=("198.51.100.77", 1))
        again = [json.loads(line) for line in buf.getvalue().splitlines()][-1]
        assert again["suppressed_since_last"] == 49
        assert "198.51.100.77" not in buf.getvalue() and '"a":1' not in buf.getvalue()
    finally:
        set_throttle(previous)
        logger.removeHandler(handler)
