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
