"""Authenticated API: chat, sessions, executions, Mentor trace explanation, quiz grading, explorer.

Policy: every query is scoped by the caller's user id taken from the verified token. A missing
resource and another user's resource both return 404. Records without a user_id (written before
ownership existed) match no query here, so no user can read or claim them.
"""
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from . import auth, mentor, sessions
from .config import settings
from .deps import db_provider
from .errors import DemoMode, ExecutionNotFound, RateLimited

ID_RE = r"^[A-Za-z0-9_\-]{1,64}$"
router = APIRouter(prefix="/api")

# name -> (owned by a user, fields returned). Fixed so the UI cannot read arbitrary collections or fields.
EXPLORER: dict[str, tuple[bool, list[str] | None]] = {
    "full_docs": (False, ["title", "source", "hash", "chunk_count"]),
    "chunked_docs": (False, ["title", "source", "chunk_index"]),
    "sessions": (True, None),
    "agent_execution_events": (True, None),
    "quiz_attempts": (True, None),
}


def require_live() -> None:
    if not settings.configured:
        raise DemoMode("Demo mode: set MONGODB_URI, OPENAI_API_KEY and VOYAGE_API_KEY in .env")


def live_user(_: Annotated[None, Depends(require_live)], user: auth.CurrentUser) -> dict[str, Any]:
    """Demo mode answers 503 first; otherwise the caller must present a valid token."""
    return user


LiveUser = Annotated[dict[str, Any], Depends(live_user)]


def chat_budget(request: Request, user: LiveUser) -> None:
    """Per-user chat budget, keyed by the verified user id and charged before any session write or graph call.

    It runs after authentication and before the handler's own checks, so malformed bodies and
    ownership denials also spend it, and a throttled caller gets 429 whether or not the session exists.
    """
    limits = request.app.state.limits
    if not limits.enabled:
        return
    decision = limits.chat_user.hit(user["_id"])
    if not decision.allowed:
        raise RateLimited(decision.retry_after, "Chat request limit reached for this account. Try again later.")


def grading_user(credentials: Annotated[Any, Depends(auth._bearer)], get_db=Depends(db_provider)) -> dict | None:
    """Quiz grading works anonymously in demo mode (no accounts); with accounts enabled it needs a token."""
    if not settings.auth_enabled:
        return None
    return auth.get_current_user(credentials, get_db)


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a client-supplied thread_id or user_id is an error, not ignored
    session_id: str | None = Field(None, pattern=ID_RE)
    message: str = Field(min_length=1, max_length=2000)


class QuizIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, int]


def _check_id(value: str) -> None:
    if not re.match(ID_RE, value):
        raise HTTPException(400, "bad id")


@router.post("/chat")
def chat(body: ChatIn, user: LiveUser, _budget: Annotated[None, Depends(chat_budget)], get_db=Depends(db_provider)):
    database = get_db()
    if body.session_id:
        session = sessions.get_owned(database, user["_id"], body.session_id)
    else:
        session = sessions.create(database, user["_id"])
    from .graph import run
    result = run(session["_id"], body.message, user_id=user["_id"])
    sessions.record_turn(database, session["_id"])
    return {**result, "session_id": session["_id"]}


@router.get("/sessions", response_model=list[sessions.PublicSession])
def list_sessions(user: LiveUser, limit: int = Query(20, ge=1, le=50), skip: int = Query(0, ge=0, le=1000),
                  get_db=Depends(db_provider)):
    return [sessions.to_public(s) for s in sessions.list_owned(get_db(), user["_id"], limit, skip)]


@router.get("/sessions/{session_id}", response_model=sessions.PublicSession)
def get_session(session_id: str, user: LiveUser, get_db=Depends(db_provider)):
    _check_id(session_id)
    return sessions.to_public(sessions.get_owned(get_db(), user["_id"], session_id))


@router.get("/executions")
def executions(user: LiveUser, limit: int = Query(20, ge=1, le=100), skip: int = Query(0, ge=0, le=1000),
               get_db=Depends(db_provider)):
    rows = (get_db()["agent_execution_events"].find({"type": "execution_end", "user_id": user["_id"]}, {"_id": 0})
            .sort("ts", -1).skip(skip).limit(limit))
    return list(rows)


def owned_events(database, user_id: str, execution_id: str) -> list[dict]:
    _check_id(execution_id)
    events = list(database["agent_execution_events"]
                  .find({"execution_id": execution_id, "user_id": user_id}, {"_id": 0}).sort("seq", 1))
    if not events:
        raise ExecutionNotFound()
    return events


@router.get("/executions/{execution_id}")
def execution(execution_id: str, user: LiveUser, get_db=Depends(db_provider)):
    return owned_events(get_db(), user["_id"], execution_id)


@router.get("/mentor/explain/{execution_id}")
def mentor_explain(execution_id: str, user: LiveUser, get_db=Depends(db_provider)):
    return mentor.explain_execution(owned_events(get_db(), user["_id"], execution_id))


@router.post("/mentor/quiz")
def mentor_grade(body: QuizIn, user: Annotated[dict | None, Depends(grading_user)], get_db=Depends(db_provider)):
    result = mentor.grade(body.answers)
    if user is not None:
        get_db()["quiz_attempts"].insert_one({"user_id": user["_id"], **result})
    return result


@router.get("/db/collections")
def collections(user: LiveUser, get_db=Depends(db_provider)):
    database = get_db()
    return [{"name": name, "scope": "owned" if owned else "shared",
             "count": database[name].count_documents({"user_id": user["_id"]}) if owned
             else database[name].estimated_document_count()}
            for name, (owned, _fields) in sorted(EXPLORER.items())]


@router.get("/db/sample/{name}")
def sample(name: str, user: LiveUser, limit: int = Query(3, ge=1, le=20), skip: int = Query(0, ge=0, le=1000),
           get_db=Depends(db_provider)):
    if name not in EXPLORER:
        raise HTTPException(403, "collection not readable")
    owned, fields = EXPLORER[name]
    query = {"user_id": user["_id"]} if owned else {}
    projection = {f: 1 for f in fields} if fields else {"embedding": 0}
    docs = list(get_db()[name].find(query, projection).skip(skip).limit(limit))
    return [{**d, "_id": str(d["_id"])} for d in docs]
