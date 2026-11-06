import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import mentor
from .config import settings

app = FastAPI(title="MongoDB AI Agent Platform", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:8000"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])
ID_RE = r"^[A-Za-z0-9_\-]{1,64}$"
READABLE = {"chunked_docs", "full_docs", "agent_execution_events", "quiz_attempts"}


class ChatIn(BaseModel):
    thread_id: str = Field(pattern=ID_RE)
    message: str = Field(min_length=1, max_length=2000)


class QuizIn(BaseModel):
    user_id: str = Field(pattern=ID_RE)
    answers: dict[str, int]


def _require_config():
    if not settings.configured:
        raise HTTPException(503, "Demo mode: set MONGODB_URI, OPENAI_API_KEY and VOYAGE_API_KEY in .env")


@app.get("/health")
def health():
    out = {"configured": settings.configured, "mode": "live" if settings.configured else "demo", "mongodb": "not_checked"}
    if settings.mongodb_uri:
        try:
            from .mongo import client
            client().admin.command("ping")
            out["mongodb"] = "ok"
        except Exception as exc:
            out["mongodb"] = f"error: {type(exc).__name__}"
    return out


@app.post("/api/chat")
def chat(body: ChatIn):
    _require_config()
    from .graph import run
    return run(body.thread_id, body.message)


@app.get("/api/executions")
def executions(limit: int = Query(20, ge=1, le=100)):
    _require_config()
    from .mongo import db
    rows = db()["agent_execution_events"].find({"type": "execution_end"}, {"_id": 0}).sort("ts", -1).limit(limit)
    return list(rows)


def _events(execution_id: str):
    from .mongo import db
    return list(db()["agent_execution_events"].find({"execution_id": execution_id}, {"_id": 0}).sort("seq", 1))


@app.get("/api/executions/{execution_id}")
def execution(execution_id: str):
    _require_config()
    if not re.match(ID_RE, execution_id):
        raise HTTPException(400, "bad id")
    return _events(execution_id)


@app.get("/api/mentor/explain/{execution_id}")
def mentor_explain(execution_id: str):
    _require_config()
    if not re.match(ID_RE, execution_id):
        raise HTTPException(400, "bad id")
    events = _events(execution_id)
    if not events:
        raise HTTPException(404, "execution not found")
    return mentor.explain_execution(events)


@app.get("/api/mentor/teach/{concept}")
def mentor_teach(concept: str):
    c = mentor.teach(concept)
    if not c:
        raise HTTPException(404, f"unknown concept; try {list(mentor.CONCEPTS)}")
    return c


@app.get("/api/mentor/quiz")
def mentor_quiz():
    return [{k: v for k, v in q.items() if k not in ("answer", "why")} for q in mentor.QUIZ]


@app.post("/api/mentor/quiz")
def mentor_grade(body: QuizIn):
    res = mentor.grade(body.answers)
    if settings.configured:
        from .mongo import db
        db()["quiz_attempts"].insert_one({"user_id": body.user_id, **res})
    return res


@app.get("/api/db/collections")
def collections():
    _require_config()
    from .mongo import db
    return [{"name": n, "count": db()[n].estimated_document_count()} for n in sorted(db().list_collection_names())]


@app.get("/api/db/sample/{name}")
def sample(name: str):
    _require_config()
    if name not in READABLE:
        raise HTTPException(403, "collection not readable")
    from .mongo import db
    docs = list(db()[name].find({}, {"embedding": 0}).limit(3))
    return [{**d, "_id": str(d["_id"])} for d in docs]


FRONT = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


@app.get("/")
def index():
    return FileResponse(FRONT)
