from app import graph
from app.tracing import Tracer


def test_history_is_owner_scoped_and_uses_finalized_public_answers(two_users, monkeypatch):
    client, database, alice, bob = two_users

    def run(session_id, message, user_id):
        tracer = Tracer(database.agent_execution_events, session_id, "primary", message, user_id=user_id)
        tracer.emit("tool_end", result_preview="private-tool-output")
        tracer.finish("success", "Approved answer", outcome="answered", citations=[{"id": "source-id"}])
        return {"answer": "Approved answer", "execution_id": tracer.execution_id}

    monkeypatch.setattr(graph, "run", run)
    first = client.post("/api/chat", headers=alice["headers"], json={"message": "First"}).json()
    sid = first["session_id"]
    client.post("/api/chat", headers=alice["headers"], json={"message": "Second", "session_id": sid})
    foreign = Tracer(database.agent_execution_events, sid, "primary", "private-bob", user_id=bob["id"])
    foreign.finish("success", "private-bob")
    path = f"/api/sessions/{sid}/history"
    response = client.get(path, headers=alice["headers"], params={"limit": 1, "skip": 1})
    assert response.status_code == 200
    row, = response.json()
    assert row["question"] == "First" and row["answer"] == "Approved answer"
    assert row["citations"] == [{"id": "source-id"}]
    assert "private-tool-output" not in response.text and "private-bob" not in response.text
    assert client.get(path, headers=bob["headers"]).status_code == 404


def test_memory_is_explicit_owner_scoped_and_excluded_after_deletion(two_users, monkeypatch):
    client, _, alice, bob = two_users
    seen = []

    def run(session_id, message, user_id, **options):
        seen.append(options.get("memory_notes"))
        return {"answer": "ok"}

    monkeypatch.setattr(graph, "run", run)
    assert client.post("/api/memory", headers=alice["headers"], json={"text": "  "}).status_code == 422
    note = client.post("/api/memory", headers=alice["headers"], json={"text": "Short examples"}).json()
    client.post("/api/memory", headers=bob["headers"], json={"text": "Bob private note"})
    path = f"/api/memory/{note['id']}"
    assert client.delete(path).status_code == 401
    assert client.delete(path, headers=bob["headers"]).status_code == 404
    assert client.get("/api/memory", headers=alice["headers"]).json() == [note]
    client.post("/api/chat", headers=alice["headers"], json={"message": "Default"})
    client.post("/api/chat/stream", headers=alice["headers"], json={"message": "Opt in", "use_memory": True})
    assert client.delete(path, headers=alice["headers"]).status_code == 204
    assert client.delete(path, headers=alice["headers"]).status_code == 404
    client.post("/api/chat", headers=alice["headers"], json={"message": "After deletion", "use_memory": True})
    assert seen == [None, ("Short examples",), ()]
