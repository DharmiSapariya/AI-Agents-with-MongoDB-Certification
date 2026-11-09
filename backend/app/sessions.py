"""Chat sessions. The id is generated here, never taken from a client, and every lookup includes the owner."""
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from .errors import SessionNotFound


class PublicSession(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    turns: int


def to_public(doc: dict[str, Any]) -> PublicSession:
    return PublicSession(id=doc["_id"], created_at=doc["created_at"], updated_at=doc["updated_at"], turns=doc["turns"])


def create(database, user_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    doc = {"_id": "s_" + uuid.uuid4().hex, "user_id": user_id, "created_at": now, "updated_at": now, "turns": 0}
    database["sessions"].insert_one(dict(doc))
    return doc


def get_owned(database, user_id: str, session_id: str) -> dict[str, Any]:
    """Missing and foreign sessions both raise SessionNotFound, so a caller cannot probe for other users' ids."""
    doc = database["sessions"].find_one({"_id": session_id, "user_id": user_id})
    if doc is None:
        raise SessionNotFound()
    return doc


def record_turn(database, session_id: str) -> None:
    database["sessions"].update_one({"_id": session_id},
                                    {"$inc": {"turns": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}})


def list_owned(database, user_id: str, limit: int, skip: int) -> list[dict[str, Any]]:
    cursor = database["sessions"].find({"user_id": user_id}).sort("updated_at", -1).skip(skip).limit(limit)
    return list(cursor)


def history(database, user_id: str, session_id: str, limit: int, skip: int) -> list[dict]:
    """Public history comes from finalized traces, avoiding raw model and tool checkpoint state."""
    get_owned(database, user_id, session_id)
    events = database["agent_execution_events"]
    scope = {"user_id": user_id, "thread_id": session_id}
    ends = list(events.find({**scope, "type": "execution_end"})
                .sort([("ts", -1), ("_id", -1)]).skip(skip).limit(limit))
    ids = [event["execution_id"] for event in ends]
    starts = events.find({**scope, "type": "execution_start", "execution_id": {"$in": ids}})
    questions = {event["execution_id"]: event["data"].get("user_input") for event in starts}
    return [{
        "execution_id": event["execution_id"], "finished_at": event["ts"],
        "question": questions.get(event["execution_id"]),
        "answer": event["data"].get("final_answer") if event["data"].get("status") == "success" else None,
        "status": event["data"].get("status"), "outcome": event["data"].get("outcome"),
        "citations": event["data"].get("citations", []),
    } for event in ends]
