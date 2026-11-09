"""Owner-scoped aggregates over recorded primary execution events."""
from datetime import datetime, timedelta, timezone


def summarize(database, user_id: str, days: int) -> dict:
    events = database["agent_execution_events"]
    scope = {"user_id": user_id, "ts": {"$gte": datetime.now(timezone.utc) - timedelta(days=days)}}

    def aggregate(kind: str, group: dict, *stages: dict) -> list[dict]:
        return list(events.aggregate([{"$match": {**scope, "type": kind}}, {"$group": group}, *stages]))

    executions = aggregate("execution_end", {
        "_id": None, "completed": {"$sum": 1},
        "errors": {"$sum": {"$cond": [{"$eq": ["$data.status", "error"]}, 1, 0]}},
        "retrieval_failures": {"$sum": {"$cond": [{"$eq": ["$data.outcome", "retrieval_failed"]}, 1, 0]}},
        "mean_duration_ms": {"$avg": "$data.duration_ms"},
    }, {"$project": {"_id": 0}})

    tools = aggregate("tool_end", {
        "_id": "$data.tool", "calls": {"$sum": 1},
        "errors": {"$sum": {"$cond": [{"$eq": ["$data.status", "error"]}, 1, 0]}},
        "mean_duration_ms": {"$avg": "$data.duration_ms"},
    }, {"$sort": {"calls": -1, "_id": 1}}, {"$limit": 20},
        {"$project": {"_id": 0, "tool": "$_id", "calls": 1, "errors": 1, "mean_duration_ms": 1}})

    usage = list(events.aggregate([
        {"$match": {**scope, "type": "agent_decision", "data.usage.total_tokens": {"$type": "number"}}},
        {"$group": {"_id": None, "reported_calls": {"$sum": 1}, "total_tokens": {"$sum": "$data.usage.total_tokens"}}},
        {"$project": {"_id": 0}},
    ]))

    return {"window_days": days, "executions": executions[0] if executions else {
        "completed": 0, "errors": 0, "retrieval_failures": 0, "mean_duration_ms": None,
    }, "top_tools": tools, "usage": usage[0] if usage and usage[0]["reported_calls"] else {"reported_calls": 0, "total_tokens": None}}
