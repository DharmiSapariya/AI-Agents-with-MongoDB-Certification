"""Independent, deterministic teaching graph with account-scoped state."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import TypedDict

from . import mentor
from .errors import ApiError
from .tracing import Tracer

Mode = Literal["teach", "watch", "step", "quiz", "challenge"]


class MentorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Mode
    session_id: str | None = Field(None, pattern=r"^mtr_[0-9a-f]{32}$")
    concept: str | None = Field(None, max_length=64)
    execution_id: str | None = Field(None, max_length=64)
    after_seq: int = Field(0, ge=0)
    answers: dict[str, int] | None = Field(None, max_length=20)
    challenge_id: str | None = Field(None, max_length=64)
    choice: int | None = Field(None, ge=0, le=20)

    @model_validator(mode="after")
    def check_mode(self):
        supplied = self.model_fields_set - {"mode", "session_id"}
        required = {
            "teach": {"concept"}, "watch": {"execution_id"}, "step": {"execution_id"},
            "quiz": {"answers"}, "challenge": {"challenge_id", "choice"},
        }[self.mode]
        allowed = required | ({"after_seq"} if self.mode == "step" else set())
        if supplied - allowed or any(getattr(self, key) is None for key in required):
            raise ValueError("Fields do not match the selected Mentor mode.")
        return self


class MentorSessionNotFound(ApiError):
    status_code, code, message = 404, "mentor_session_not_found", "Mentor session not found."


class MentorState(TypedDict, total=False):
    mode: Mode
    lesson: dict
    events: list[dict]
    after_seq: int
    result: dict
    answers: dict[str, int]
    challenge_id: str
    choice: int


_SAFE_FIELDS = {
    "agent_decision": ("final", "latency_ms"),
    "tool_start": ("tool",),
    "tool_end": ("tool", "status", "duration_ms", "error_category"),
    "db_operation": ("op", "collection", "returned", "latency_ms"),
    "execution_end": ("status", "duration_ms", "fully_recorded", "outcome"),
    "error": ("error_category",),
}


def safe_event(event: dict) -> dict:
    kind = event["type"]
    data = event.get("data", {})
    safe = {key: data[key] for key in _SAFE_FIELDS.get(kind, ()) if key in data}
    if kind == "agent_decision":
        safe["tool_calls"] = [{"name": call["name"]} for call in data.get("tool_calls", [])[:20]]
    return {"seq": event["seq"], "type": kind, "node": event.get("node"), "data": safe}


def _teach(state: MentorState) -> dict:
    return {"result": {"lesson": state["lesson"]}}


def _watch(state: MentorState) -> dict:
    events = state["events"]
    return {"result": {**mentor.explain_execution(events[:100]), "truncated": len(events) > 100}}


def _step(state: MentorState) -> dict:
    events = [event for event in state["events"] if event["seq"] > state["after_seq"]]
    steps = mentor.explain_execution(events[:1])["steps"]
    return {"result": {"step": steps[0] if steps else None, "has_more": len(events) > 1}}


def _quiz(state: MentorState) -> dict:
    return {"result": mentor.grade(state["answers"])}


def _challenge(state: MentorState) -> dict:
    return {"result": mentor.challenge(state["challenge_id"], state["choice"])}


def _build():
    graph = StateGraph(MentorState)
    graph.add_node("teach", _teach)
    graph.add_node("watch", _watch)
    graph.add_node("step", _step)
    graph.add_node("quiz", _quiz)
    graph.add_node("challenge", _challenge)
    modes = ("teach", "watch", "step", "quiz", "challenge")
    graph.add_conditional_edges(START, lambda state: state["mode"], {mode: mode for mode in modes})
    for mode in modes:
        graph.add_edge(mode, END)
    return graph.compile()


_workflow = _build()


def owned_session(database, user_id: str, session_id: str) -> dict:
    row = database["mentor_sessions"].find_one({"_id": session_id, "user_id": user_id})
    if row is None:
        raise MentorSessionNotFound()
    return row


def run(database, user_id: str, request: MentorIn, state: MentorState) -> dict:
    session_id = request.session_id or f"mtr_{uuid4().hex}"
    if request.session_id:
        owned_session(database, user_id, session_id)
    else:
        database["mentor_sessions"].insert_one({
            "_id": session_id, "user_id": user_id, "created_at": datetime.now(timezone.utc),
        })
    tracer = Tracer(database["mentor_events"], session_id, "mentor", "", user_id=user_id)
    tracer.emit("mentor_mode", node=request.mode, mode=request.mode)
    try:
        result = _workflow.invoke(state)["result"]
        database["mentor_runs"].insert_one({
            "session_id": session_id, "user_id": user_id, "run_id": tracer.execution_id,
            "mode": request.mode, "execution_id": request.execution_id, "concept": request.concept, "result": result, "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        tracer.finish("error")
        raise
    tracer.finish("success")
    return {"session_id": session_id, "run_id": tracer.execution_id, **result}


def history(database, user_id: str, session_id: str, limit: int, skip: int) -> list[dict]:
    owned_session(database, user_id, session_id)
    return list(database["mentor_runs"].find({"session_id": session_id, "user_id": user_id}, {"_id": 0, "user_id": 0})
                .sort([("created_at", -1), ("_id", -1)]).skip(skip).limit(limit))


def progress(database, user_id: str) -> dict:
    runs = database["mentor_runs"]
    scope = {"user_id": user_id}
    quizzes = list(runs.aggregate([
        {"$match": {**scope, "mode": "quiz"}},
        {"$group": {"_id": None, "attempts": {"$sum": 1}, "best_score": {"$max": "$result.score"}}},
        {"$project": {"_id": 0}},
    ]))
    return {
        "lessons_viewed": sorted(runs.distinct("concept", {**scope, "mode": "teach"})),
        "quiz": quizzes[0] if quizzes else {"attempts": 0, "best_score": None},
        "challenges_passed": sorted(runs.distinct(
            "result.challenge_id", {**scope, "mode": "challenge", "result.passed": True})),
    }
