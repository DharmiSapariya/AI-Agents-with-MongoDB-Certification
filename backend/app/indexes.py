"""Regular (non-vector) indexes, matched to the queries the app actually runs."""
from pymongo import ASCENDING, DESCENDING


def ensure_indexes(database) -> list[str]:
    created = [
        # /api/executions/{id}: all events of one run in order
        database["agent_execution_events"].create_index([("execution_id", ASCENDING), ("seq", ASCENDING)]),
        # /api/executions: newest finished runs
        database["agent_execution_events"].create_index([("type", ASCENDING), ("ts", DESCENDING)]),
        database["agent_execution_events"].create_index([("thread_id", ASCENDING), ("ts", DESCENDING)]),
        # get_page_content_for_summarization looks pages up by exact title; ingestion upserts by title
        database["full_docs"].create_index([("title", ASCENDING)], unique=True),
        database["chunked_docs"].create_index([("title", ASCENDING)]),
        # owner-scoped reads: /api/executions and /api/sessions
        database["agent_execution_events"].create_index([("user_id", ASCENDING), ("type", ASCENDING), ("ts", DESCENDING)]),
        database["agent_execution_events"].create_index(
            [("user_id", ASCENDING), ("thread_id", ASCENDING), ("type", ASCENDING), ("ts", DESCENDING), ("_id", DESCENDING)]),
        database["user_memories"].create_index([("user_id", ASCENDING), ("created_at", DESCENDING), ("_id", DESCENDING)]),
        database["sessions"].create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)]),
        database["quiz_attempts"].create_index([("user_id", ASCENDING)]),
        # registration relies on this to reject concurrent duplicates
        database["users"].create_index([("email", ASCENDING)], unique=True, name="email_unique"),
    ]
    return created
