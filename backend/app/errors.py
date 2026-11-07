"""Consistent API errors and classification of failures from MongoDB, the LLM and embeddings.

Clients get {"error": {"code", "message", "request_id"}}. Details (exception types, redacted
tracebacks) go to the server log only.
"""
import logging
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo import errors as mongo_errors
from starlette.exceptions import HTTPException as StarletteHTTPException

from .context import request_id_var
from .logging_config import log

logger = logging.getLogger("app.errors")

HTTP_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
              405: "method_not_allowed", 413: "payload_too_large", 422: "validation_error",
              429: "rate_limited"}


class ApiError(Exception):
    status_code = 500
    code = "internal_error"
    message = "Internal server error"

    def __init__(self, message: str | None = None, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code


class DemoMode(ApiError):
    status_code, code = 503, "demo_mode"


class DatabaseUnavailable(ApiError):
    status_code, code, message = 503, "database_unavailable", "The database is currently unreachable."


class UpstreamTimeout(ApiError):
    status_code, code, message = 504, "timeout", "An upstream service timed out."


class LLMProviderError(ApiError):
    status_code, code, message = 502, "llm_provider_error", "The language model provider failed."


class EmbeddingError(ApiError):
    status_code, code, message = 502, "embedding_provider_error", "The embedding provider failed."


class ExecutionLimitExceeded(ApiError):
    status_code, code = 422, "execution_limit_exceeded"
    message = "The agent reached its step limit before finishing. Try a simpler request."


def error_body(code: str, message: str, details: list | None = None) -> dict:
    body: dict[str, Any] = {"code": code, "message": message, "request_id": request_id_var.get()}
    if details:
        body["details"] = details
    return {"error": body}


def _library_errors() -> dict[str, tuple[type[Exception], ...]]:
    """Provider exception classes, looked up lazily so a missing optional SDK cannot break import."""
    found: dict[str, tuple[type[Exception], ...]] = {"openai": (), "openai_timeout": (), "voyage": (), "graph": ()}
    try:
        import openai
        found["openai"], found["openai_timeout"] = (openai.OpenAIError,), (openai.APITimeoutError,)
    except ImportError:
        pass
    try:
        from voyageai.error import VoyageError
        found["voyage"] = (VoyageError,)
    except ImportError:
        pass
    try:
        from langgraph.errors import GraphRecursionError
        found["graph"] = (GraphRecursionError,)
    except ImportError:
        pass
    return found


LIBS = _library_errors()
KNOWN_EXCEPTIONS: tuple[type[Exception], ...] = (
    ApiError, mongo_errors.PyMongoError, TimeoutError, *LIBS["openai"], *LIBS["voyage"], *LIBS["graph"])


def _classify_one(exc: BaseException) -> ApiError | None:
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, (mongo_errors.NetworkTimeout, mongo_errors.ExecutionTimeout)):
        return UpstreamTimeout("The database timed out.", code="database_timeout")
    if isinstance(exc, mongo_errors.ConnectionFailure):  # includes ServerSelectionTimeoutError
        return DatabaseUnavailable()
    if isinstance(exc, mongo_errors.PyMongoError):
        return ApiError("A database operation failed.", code="database_error")
    if LIBS["openai_timeout"] and isinstance(exc, LIBS["openai_timeout"]):
        return UpstreamTimeout("The language model timed out.", code="llm_timeout")
    if LIBS["openai"] and isinstance(exc, LIBS["openai"]):
        return LLMProviderError()
    if LIBS["voyage"] and isinstance(exc, LIBS["voyage"]):
        return EmbeddingError()
    if LIBS["graph"] and isinstance(exc, LIBS["graph"]):
        return ExecutionLimitExceeded()
    if isinstance(exc, TimeoutError):
        return UpstreamTimeout()
    return None


def classify(exc: BaseException) -> ApiError:
    """Map any exception to an ApiError, following __cause__/__context__ for wrapped failures."""
    current: BaseException | None = exc
    for _ in range(5):
        if current is None:
            break
        if (match := _classify_one(current)) is not None:
            return match
        current = current.__cause__ or current.__context__
    return ApiError()


async def _handle_known(request: Request, exc: Exception) -> JSONResponse:
    err = classify(exc)
    fields = {"error_category": err.code, "status": err.status_code, "exc_type": type(exc).__name__}
    if err.status_code >= 500:
        logger.error("request_failed", exc_info=exc, extra={"fields": fields})
    else:
        log(logger, logging.WARNING, "request_rejected", **fields)
    return JSONResponse(error_body(err.code, err.message), status_code=err.status_code)


async def _handle_http(request: Request, error: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, error)
    code = HTTP_CODES.get(exc.status_code, f"http_{exc.status_code}")
    message = exc.detail if isinstance(exc.detail, str) else code.replace("_", " ")
    return JSONResponse(error_body(code, message), status_code=exc.status_code, headers=exc.headers)


async def _handle_validation(request: Request, error: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, error)
    # Report where and why, never the submitted value (pydantic's "input" field).
    details = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(error_body("validation_error", "Request validation failed.", details), status_code=422)


def install_handlers(app: FastAPI) -> None:
    for exc_class in KNOWN_EXCEPTIONS:
        app.add_exception_handler(exc_class, _handle_known)
    app.add_exception_handler(StarletteHTTPException, _handle_http)
    app.add_exception_handler(RequestValidationError, _handle_validation)
