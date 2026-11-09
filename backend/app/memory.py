"""Explicitly saved, account-scoped notes for optional personalization."""
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import TypedDict

from .errors import ApiError


class MemoryOptions(TypedDict, total=False):
    memory_notes: tuple[str, ...]


class MemoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        if not (text := value.strip()):
            raise ValueError("Memory text cannot be blank.")
        return text


class PublicMemory(BaseModel):
    id: str
    text: str
    created_at: datetime


class MemoryNotFound(ApiError):
    status_code, code, message = 404, "memory_not_found", "Memory not found."


def save(database, user_id: str, text: str) -> PublicMemory:
    now = datetime.now(timezone.utc)
    recorded_at = now.replace(microsecond=now.microsecond // 1000 * 1000)
    record = PublicMemory(id=f"m_{uuid4().hex}", text=text, created_at=recorded_at)
    database["user_memories"].insert_one({
        "_id": record.id, "user_id": user_id, "text": record.text, "created_at": record.created_at,
    })
    return record


def list_owned(database, user_id: str, limit: int, skip: int = 0) -> list[PublicMemory]:
    rows = database["user_memories"].find({"user_id": user_id}, {"text": 1, "created_at": 1})
    return [PublicMemory(id=row["_id"], text=row["text"], created_at=row["created_at"].replace(tzinfo=timezone.utc))
            for row in rows.sort([("created_at", -1), ("_id", -1)]).skip(skip).limit(limit)]


def delete(database, user_id: str, memory_id: str) -> None:
    result = database["user_memories"].delete_one({"_id": memory_id, "user_id": user_id})
    if not result.deleted_count:
        raise MemoryNotFound()
