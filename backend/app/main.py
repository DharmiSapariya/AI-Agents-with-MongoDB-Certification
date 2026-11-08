import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import health, mentor, mongo
from .config import settings
from .errors import install_handlers
from .logging_config import configure_logging, log
from .middleware import RequestIdMiddleware
from .routes_api import router as api_router
from .routes_auth import router as auth_router

configure_logging(settings.log_level, settings.log_redact_patterns)

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create the MongoDB client once in live mode; start even if Atlas is unreachable so /health can say so."""
    log(logger, logging.INFO, "startup", mode=settings.mode, missing=settings.missing_credentials)
    if settings.configured:
        mongo.connect()
        state = await run_in_threadpool(health.database_state)
        log(logger, logging.INFO if state["state"] == "connected" else logging.ERROR,
            "database_check_at_startup", **state)
    if not settings.auth_enabled:
        log(logger, logging.INFO, "auth_unavailable", reason=settings.auth_unavailable_reason)
    yield
    mongo.close()


app = FastAPI(title="MongoDB AI Agent Platform", version="0.1.0", lifespan=lifespan)
install_handlers(app)
app.include_router(auth_router)
app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:8000"],
                   allow_methods=["GET", "POST"], allow_headers=["*"], expose_headers=["X-Request-ID"])
app.add_middleware(RequestIdMiddleware)


@app.get("/health")
def health_check():
    body, status = health.report()
    return JSONResponse(body, status_code=status)


@app.get("/api/mentor/teach/{concept}")
def mentor_teach(concept: str):
    c = mentor.teach(concept)
    if not c:
        raise HTTPException(404, f"unknown concept; try {list(mentor.CONCEPTS)}")
    return c


@app.get("/api/mentor/quiz")
def mentor_quiz():
    return [{k: v for k, v in q.items() if k not in ("answer", "why")} for q in mentor.QUIZ]


FRONT = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


@app.get("/")
def index():
    return FileResponse(FRONT)
