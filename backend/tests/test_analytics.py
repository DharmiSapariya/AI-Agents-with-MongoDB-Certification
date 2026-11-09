from datetime import datetime, timedelta, timezone


def test_analytics_uses_only_owned_events_in_the_requested_window(two_users):
    client, database, alice, bob = two_users
    now = datetime.now(timezone.utc)

    def event(user, kind, data, age=0):
        return {"user_id": user, "type": kind, "data": data, "ts": now - timedelta(days=age)}

    database.agent_execution_events.insert_many([
        event(alice["id"], "execution_end", {"status": "success", "duration_ms": 10, "outcome": "retrieval_failed"}),
        event(alice["id"], "execution_end", {"status": "error", "duration_ms": 30}),
        event(alice["id"], "tool_end", {"tool": "lookup", "status": "error", "duration_ms": 12}),
        event(alice["id"], "agent_decision", {"usage": {"total_tokens": 14}}),
        event(alice["id"], "agent_decision", {"usage": None}),
        event(alice["id"], "agent_decision", {"usage": {"total_tokens": 8}}, age=8),
        event(bob["id"], "execution_end", {"status": "success", "duration_ms": 90}),
        event(None, "execution_end", {"status": "success", "duration_ms": 90}),
    ])
    response = client.get("/api/analytics/summary", headers=alice["headers"])
    assert response.status_code == 200
    assert response.json() == {
        "window_days": 7,
        "executions": {"completed": 2, "errors": 1, "retrieval_failures": 1, "mean_duration_ms": 20},
        "top_tools": [{"tool": "lookup", "calls": 1, "errors": 1, "mean_duration_ms": 12}],
        "usage": {"reported_calls": 1, "total_tokens": 14},
    }
    assert client.get("/api/analytics/summary", headers=bob["headers"]).json()["usage"] == {
        "reported_calls": 0, "total_tokens": None,
    }
