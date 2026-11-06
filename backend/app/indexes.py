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
        database["quiz_attempts"].create_index([("user_id", ASCENDING)]),
    ]
    return created
