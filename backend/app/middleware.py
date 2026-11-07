"""Request ID propagation and one access-log line per request."""
import logging
import re
import time
import uuid

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .context import request_id_var
from .logging_config import log

logger = logging.getLogger("app.http")
HEADER = "x-request-id"
VALID_ID = re.compile(r"^[A-Za-z0-9._\-]{8,64}$")


def _incoming_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == HEADER.encode():
            candidate = value.decode("latin-1")
            return candidate if VALID_ID.match(candidate) else None
    return None


class RequestIdMiddleware:
    """Pure ASGI so the id is set before routing and visible in worker threads."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = _incoming_id(scope)
        request_id = supplied or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                message.setdefault("headers", []).append((HEADER.encode(), request_id.encode()))
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_id)
            except Exception:
                logger.exception("unhandled_exception", extra={"fields": {"error_category": "internal"}})
                if response_started:
                    raise
                body = {"error": {"code": "internal_error", "message": "Internal server error",
                                  "request_id": request_id}}
                await JSONResponse(body, status_code=500)(scope, receive, send_with_id)
        finally:
            route = scope.get("route")
            log(logger, logging.INFO, "request_completed", method=scope["method"],
                path=getattr(route, "path", scope["path"]), status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                request_id_supplied=supplied is not None)
            request_id_var.reset(token)
