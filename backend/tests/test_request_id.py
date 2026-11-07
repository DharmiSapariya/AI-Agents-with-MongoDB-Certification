import asyncio
import io
import json
import logging

import httpx
import pytest
from fastapi import FastAPI

from app.context import request_id_var
from app.logging_config import JsonFormatter
from app.main import app as real_app
from app.middleware import RequestIdMiddleware
from app.tracing import Tracer


def make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/id")
    async def current_id():
        await asyncio.sleep(0.01)
        return {"seen": request_id_var.get()}

    @app.get("/boom")
    def boom():
        raise RuntimeError("failed to reach mongodb+srv://u:hunter2@h.example.net/db")

    return app


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                             base_url="http://test")


async def get(app, path, **headers):
    async with client(app) as c:
        return await c.get(path, headers={k: v.encode("latin-1") for k, v in headers.items()})


@pytest.fixture
def http_log():
    buf = io.StringIO()
    logger = logging.getLogger("app.http")
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield buf
    logger.removeHandler(handler)


def rows(buf):
    return [json.loads(line) for line in buf.getvalue().splitlines()]


def test_generates_an_id_when_none_supplied():
    resp = asyncio.run(get(make_app(), "/id"))
    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == resp.json()["seen"]
    assert len(resp.headers["x-request-id"]) == 32


def test_valid_supplied_id_is_kept():
    resp = asyncio.run(get(make_app(), "/id", **{"X-Request-ID": "client-req-0001"}))
    assert resp.headers["x-request-id"] == "client-req-0001" == resp.json()["seen"]


@pytest.mark.parametrize("bad", ["short", "has spaces in it!", "x" * 65, "ünïcode-request-id", "a/b\\c-12345678"])
def test_invalid_supplied_id_is_replaced(bad):
    resp = asyncio.run(get(make_app(), "/id", **{"X-Request-ID": bad}))
    assert resp.headers["x-request-id"] != bad
    assert resp.headers["x-request-id"] == resp.json()["seen"]


def test_unhandled_error_returns_generic_body_with_id_and_logs_it(http_log):
    resp = asyncio.run(get(make_app(), "/boom", **{"X-Request-ID": "client-req-0002"}))
    assert resp.status_code == 500
    assert resp.headers["x-request-id"] == "client-req-0002"
    body = resp.json()["error"]
    assert body == {"code": "internal_error", "message": "Internal server error", "request_id": "client-req-0002"}
    assert "hunter2" not in resp.text and "Traceback" not in resp.text
    logged = rows(http_log)
    assert all(r["request_id"] == "client-req-0002" for r in logged)
    assert "hunter2" not in http_log.getvalue()
    assert [r["event"] for r in logged] == ["unhandled_exception", "request_completed"]
    assert logged[1]["status"] == 500 and logged[1]["duration_ms"] >= 0


def test_access_log_has_route_template_not_query_string(http_log):
    asyncio.run(get(real_app, "/api/mentor/teach/agent?token=abc123"))
    row = rows(http_log)[-1]
    assert row["event"] == "request_completed" and row["status"] == 200
    assert row["path"] == "/api/mentor/teach/{concept}" and "abc123" not in http_log.getvalue()


def test_real_app_returns_header_on_success_and_validation_error():
    ok = asyncio.run(get(real_app, "/api/mentor/quiz"))
    bad = asyncio.run(get(real_app, "/api/executions?limit=0"))
    assert ok.headers["x-request-id"] and bad.status_code in (422, 503)
    assert bad.headers["x-request-id"]


def test_concurrent_requests_never_share_ids():
    app = make_app()

    async def many():
        async with client(app) as c:
            supplied = [f"supplied-id-{i:04d}" for i in range(15)]
            calls = [c.get("/id", headers={"X-Request-ID": rid}) for rid in supplied]
            calls += [c.get("/id") for _ in range(15)]
            return supplied, await asyncio.gather(*calls)

    supplied, responses = asyncio.run(many())
    assert all(r.headers["x-request-id"] == r.json()["seen"] for r in responses)
    assert [r.headers["x-request-id"] for r in responses[:15]] == supplied
    assert len({r.headers["x-request-id"] for r in responses}) == 30
    assert request_id_var.get() is None


class Col:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        self.docs.append(doc)


def test_request_id_is_recorded_on_execution_events():
    col = Col()
    token = request_id_var.set("client-req-0003")
    try:
        tracer = Tracer(col, "thread-1", "primary", "hi")
        tracer.finish("success", "ok")
    finally:
        request_id_var.reset(token)
    assert {d["request_id"] for d in col.docs} == {"client-req-0003"}
