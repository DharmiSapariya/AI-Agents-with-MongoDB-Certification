"""Request protection that runs before routing: per-IP rate limits and request body caps.

Order of work for each request: pick the policy from method and path, charge the IP bucket,
check the declared Content-Length, buffer the body up to the cap, then call the app. A rejected
request therefore never reaches JSON parsing, authentication, Argon2, the graph, providers or the
database. The per-user chat budget lives in routes_api (it needs the verified identity).

The client address is `scope["client"]` and nothing else: Forwarded and X-Forwarded-For are never
read here. If the server sits behind a reverse proxy, uvicorn's --forwarded-allow-ips decides whether
to rewrite that address from the proxy's headers (see README).
"""
import ipaddress
import logging
import time
from dataclasses import dataclass
from typing import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings
from .errors import error_body
from .limiter import RateLimiter
from .logging_config import log_expected

logger = logging.getLogger("app.protection")
BODYLESS_METHODS = {"GET", "HEAD", "OPTIONS", "DELETE"}


@dataclass
class Route:
    policy: str
    ip_limiter: RateLimiter | None
    body_cap: int


@dataclass
class Limits:
    """All limiter state for one app instance, kept on app.state.limits."""

    enabled: bool
    register_ip: RateLimiter
    login_ip: RateLimiter
    chat_ip: RateLimiter
    chat_user: RateLimiter
    read_ip: RateLimiter
    max_body_bytes: int
    max_auth_body_bytes: int

    @classmethod
    def from_settings(cls, s: Settings, clock: Callable[[], float] = time.monotonic) -> "Limits":
        def bucket(capacity: int, window_s: float) -> RateLimiter:
            return RateLimiter(capacity, window_s, s.rate_limit_max_keys, clock)

        return cls(
            enabled=s.rate_limit_enabled,
            register_ip=bucket(s.rate_register_ip_per_hour, 3600),
            login_ip=bucket(s.rate_login_ip_per_min, 60),
            chat_ip=bucket(s.rate_chat_ip_per_min, 60),
            chat_user=bucket(s.rate_chat_user_per_min, 60),
            read_ip=bucket(s.rate_read_ip_per_min, 60),
            max_body_bytes=s.max_body_bytes,
            max_auth_body_bytes=s.max_auth_body_bytes,
        )

    def route_for(self, method: str, path: str) -> Route:
        if method == "POST" and path == "/api/auth/register":
            return Route("register", self.register_ip, self.max_auth_body_bytes)
        if method == "POST" and path == "/api/auth/login":
            return Route("login", self.login_ip, self.max_auth_body_bytes)
        if method == "POST" and path == "/api/chat":
            return Route("chat", self.chat_ip, self.max_body_bytes)
        if path.startswith("/api/"):
            return Route("read", self.read_ip, self.max_body_bytes)
        return Route("exempt", None, self.max_body_bytes)  # /health, /, docs: probes must not be throttled


def client_key(scope: Scope) -> str:
    """Limiter key for the peer: the ASGI client host, IPv6 grouped by /64, 'unknown' if absent.

    Requests with no client address share one bucket (fail closed). Raw keys are never logged.
    """
    client = scope.get("client")
    host = client[0] if client else None
    if not host:
        return "unknown"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return str(host)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))  # one customer usually owns a /64
    return str(ip)


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _has_body(scope: Scope) -> bool:
    if scope["method"] not in BODYLESS_METHODS:
        return True
    names = {name for name, _ in scope["headers"]}
    return b"transfer-encoding" in names or (_declared_length(scope) or 0) > 0


class ProtectionMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limits: Limits = scope["app"].state.limits
        method = scope["method"]
        route = limits.route_for(method, scope["path"])

        if limits.enabled and route.ip_limiter is not None and method != "OPTIONS":  # preflights are not API calls
            decision = route.ip_limiter.hit(client_key(scope))
            if not decision.allowed:
                message = ("Too many requests from this address. Try again later."
                           if decision.reason is None else "The server is busy. Try again later.")
                await self._reject(scope, receive, send, 429, "rate_limited", message,
                                   {"Retry-After": str(decision.retry_after)}, route.policy, "ip")
                return

        declared = _declared_length(scope)
        if declared is not None and declared > route.body_cap:
            await self._too_large(scope, receive, send, route)
            return
        if not _has_body(scope):
            await self.app(scope, receive, send)
            return

        body = await self._buffer(receive, route.body_cap)
        if body is None:  # over the cap while receiving
            await self._too_large(scope, receive, send, route)
            return
        if body is False:  # client went away mid-body
            return
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()  # later calls only see disconnect

        await self.app(scope, replay, send)

    @staticmethod
    async def _buffer(receive: Receive, cap: int) -> bytes | None | bool:
        """Read the whole body, never holding more than cap bytes. None: too large. False: disconnected."""
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return False
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > cap:
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)

    async def _too_large(self, scope: Scope, receive: Receive, send: Send, route: Route) -> None:
        await self._reject(scope, receive, send, 413, "payload_too_large",
                           f"Request body exceeds the {route.body_cap} byte limit.",
                           {"Connection": "close"}, route.policy, "body")

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, status: int, code: str, message: str,
                      headers: dict[str, str], policy: str, kind: str) -> None:
        log_expected(logger, logging.WARNING, "request_rejected", code, status=status, policy=policy, limit=kind)
        await JSONResponse(error_body(code, message), status_code=status, headers=headers)(scope, receive, send)
