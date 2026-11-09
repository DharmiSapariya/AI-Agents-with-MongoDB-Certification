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

Mode = Literal["teach", "watch", "step"]


class MentorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Mode
    session_id: str | None = Field(None, pattern=r"^mtr_[0-9a-f]{32}$")
    concept: str | None = Field(None, max_length=64)
    execution_id: str | None = Field(None, max_length=64)
    after_seq: int = Field(0, ge=0)

    @model_validator(mode="after")
    def check_mode(self):
        if self.mode == "teach":
            if not self.concept or self.execution_id or self.after_seq:
                raise ValueError("Teach requires a concept.")
        elif not self.execution_id or self.concept or (self.mode == "watch" and self.after_seq):
            raise ValueError("Trace modes require an execution ID. Only step accepts a sequence cursor.")
        return self


class MentorSessionNotFound(ApiError):
    status_code, code, message = 404, "mentor_session_not_found", "Mentor session not found."


class MentorState(TypedDict, total=False):
    mode: Mode
    lesson: dict
    events: list[dict]
    after_seq: int
    result: dict


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


def _build():
    graph = StateGraph(MentorState)
    graph.add_node("teach", _teach)
    graph.add_node("watch", _watch)
    graph.add_node("step", _step)
    graph.add_conditional_edges(START, lambda state: state["mode"],
                                {"teach": "teach", "watch": "watch", "step": "step"})
    for mode in ("teach", "watch", "step"):
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
