"""Health reporting. 'connected' is only reported after a real ping succeeds."""
import logging

from . import mongo
from .config import settings
from .logging_config import log

logger = logging.getLogger("app.health")


def database_state() -> dict:
    """One of: demo, not_configured, unreachable, connected."""
    if settings.app_mode == "demo":
        return {"state": "demo"}
    if not settings.mongodb_uri:
        return {"state": "not_configured"}
    try:
        mongo.ping()
    except Exception as exc:
        log(logger, logging.WARNING, "database_unreachable", exc_type=type(exc).__name__)  # detail stays in the log
        return {"state": "unreachable"}
    return {"state": "connected"}


def report() -> tuple[dict, int]:
    """Return (body, http_status). Live mode without a working database is a 503."""
    database = database_state()
    body = {
        "status": "ok",
        "mode": settings.mode,
        "mongodb": database["state"],
        "auth": "enabled" if settings.auth_enabled else "unavailable",
        "database": database,
    }
    if settings.configured and database["state"] != "connected":
        body["status"] = "degraded"
        return body, 503
    return body, 200
