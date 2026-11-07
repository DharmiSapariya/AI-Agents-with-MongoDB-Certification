"""MongoDB client lifecycle: one client per process, created at startup and closed at shutdown.

The FastAPI lifespan calls connect() and close(). Scripts and tests may call client()/db()
directly; set_client() swaps in a fake or mock client without touching callers.
"""
import logging
import threading

from pymongo import MongoClient
from pymongo.database import Database

from .config import settings
from .logging_config import log

logger = logging.getLogger("app.mongo")
_lock = threading.Lock()
_client: MongoClient | None = None


class DatabaseNotConfigured(RuntimeError):
    """MONGODB_URI is not set."""


def connect() -> MongoClient:
    """Create the shared client if needed. Does not contact the server (PyMongo connects lazily)."""
    global _client
    with _lock:
        if _client is None:
            if not settings.mongodb_uri:
                raise DatabaseNotConfigured("MONGODB_URI is not set")
            _client = MongoClient(
                settings.mongodb_uri,
                serverSelectionTimeoutMS=settings.mongo_timeout_ms,
                connectTimeoutMS=settings.mongo_timeout_ms,
                socketTimeoutMS=settings.mongo_socket_timeout_ms,
                maxPoolSize=settings.mongo_max_pool_size,
                appname="mongodb-ai-agent-platform",
            )
        return _client


def client() -> MongoClient:
    return _client or connect()


def db() -> Database:
    return client()[settings.db_name]


def set_client(replacement: MongoClient | None) -> MongoClient | None:
    """Install a client (tests, dependency injection) and return the previous one."""
    global _client
    with _lock:
        previous, _client = _client, replacement
    return previous


def close() -> None:
    global _client
    with _lock:
        current, _client = _client, None
    if current is not None:
        current.close()
        log(logger, logging.INFO, "mongo_client_closed")


def ping() -> None:
    """Round-trip to the server; raises a PyMongoError if it cannot be reached."""
    client().admin.command("ping")
