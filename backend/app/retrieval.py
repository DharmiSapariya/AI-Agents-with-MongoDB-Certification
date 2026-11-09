"""Atlas index readiness and the vector query used by the agent."""
from typing import Any

from pymongo.errors import OperationFailure

from .config import Settings
from .errors import ApiError


class VectorIndexUnavailable(ApiError):
    status_code, code = 503, "vector_index_unavailable"


def vector_index_definition(config: Settings) -> dict:
    return {"fields": [{"type": "vector", "path": "embedding",
                        "numDimensions": config.embedding_dims, "similarity": "cosine"}]}


def index_state(collection, config: Settings) -> str:
    row = next(iter(collection.list_search_indexes(name=config.vector_index)), None)
    if row is None or row.get("status") == "DOES_NOT_EXIST":
        return "missing"
    definition = row.get("latestDefinition") or {}
    field = vector_index_definition(config)["fields"][0]
    matching = any(all(candidate.get(key) == value for key, value in field.items())
                   for candidate in definition.get("fields", []))
    if row.get("type") != "vectorSearch" or not matching:
        return "incompatible"
    if row.get("status") == "FAILED":
        return "failed"
    if row.get("status") == "READY" and row.get("queryable") is True:
        return "ready"
    return "building"


def vector_search(collection, config: Settings, vector: list[float], *, limit: int = 5) -> list[dict[str, Any]]:
    try:
        state = index_state(collection, config)
        if state != "ready":
            raise VectorIndexUnavailable(f"Vector index is {state}. Check the index setup guide.")
        pipeline = [
            {"$vectorSearch": {"index": config.vector_index, "path": "embedding",
                               "queryVector": vector, "numCandidates": max(150, limit), "limit": limit}},
            {"$project": {"_id": 1, "title": 1, "body": 1, "source": 1,
                          "chunk_index": 1, "score": {"$meta": "vectorSearchScore"}}},
        ]
        rows = list(collection.aggregate(pipeline))
    except OperationFailure as exc:
        if exc.code == 13:
            raise VectorIndexUnavailable("Vector search or index inspection is not permitted.") from exc
        raise
    return [row for row in rows if row["score"] >= config.vector_min_score]
