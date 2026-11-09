from app.tracing import Tracer


def test_mentor_has_separate_sessions_and_reads_only_owned_trace_metadata(two_users):
    client, database, alice, bob = two_users
    tracer = Tracer(database.agent_execution_events, "primary-thread", "primary", "private-question", user_id=alice["id"])
    tracer.emit("tool_end", node="tools", tool="lookup", status="ok", result_preview="private-result")
    tracer.finish("success", "private-answer")
    before = list(database.agent_execution_events.find())
    path = "/api/mentor/run"
    body = {"mode": "watch", "execution_id": tracer.execution_id}
    assert client.post(path, headers=bob["headers"], json=body).status_code == 404
    assert database.mentor_sessions.count_documents({}) == 0

    response = client.post(path, headers=alice["headers"], json=body)
    assert response.status_code == 200
    assert "private-" not in response.text
    result = response.json()
    assert [step["seq"] for step in result["steps"]] == [1, 2, 3]
    assert result["steps"][1]["recorded"] == {"tool": "lookup", "status": "ok"}
    sid = result["session_id"]
    assert database.mentor_events.count_documents({"thread_id": sid, "user_id": alice["id"]}) == 3

    step_request = {"mode": "step", "session_id": sid, "execution_id": tracer.execution_id, "after_seq": 2}
    step = client.post(path, headers=alice["headers"], json=step_request)
    assert step.status_code == 200
    assert step.json()["step"]["seq"] == 3 and step.json()["has_more"] is False
    step_request["after_seq"] = 3
    assert client.post(path, headers=alice["headers"], json=step_request).json()["step"] is None
    assert client.post(path, headers=bob["headers"], json={
        "mode": "teach", "concept": "agent", "session_id": sid,
    }).status_code == 404
    history = f"/api/mentor/sessions/{sid}"
    assert client.get(history, headers=bob["headers"]).status_code == 404
    assert len(client.get(history, headers=alice["headers"]).json()) == 3
    assert list(database.agent_execution_events.find()) == before


def test_mentor_quiz_challenges_and_progress_are_deterministic_and_owner_scoped(two_users):
    client, _, alice, bob = two_users
    path = "/api/mentor/run"
    result = client.post(path, headers=alice["headers"], json={"mode": "teach", "concept": "agent"}).json()
    assert result["lesson"]["file"] == "backend/app/graph.py"
    sid = result["session_id"]
    catalog = client.get("/api/mentor/challenges").json()
    assert all("answer" not in item for item in catalog)
    assert client.post(path, headers=alice["headers"], json={
        "mode": "quiz", "session_id": sid, "answers": {"q1": 1, "q2": 0, "q3": 1},
    }).json()["score"] == 3
    challenge = {"mode": "challenge", "session_id": sid, "challenge_id": "trace-routing"}
    assert client.post(path, headers=alice["headers"], json={**challenge, "choice": 2}).json()["passed"] is False
    assert client.post(path, headers=alice["headers"], json={**challenge, "choice": 0}).json()["passed"] is True
    assert client.get("/api/mentor/progress", headers=alice["headers"]).json() == {
        "lessons_viewed": ["agent"], "quiz": {"attempts": 1, "best_score": 3}, "challenges_passed": ["trace-routing"],
    }
    assert client.get("/api/mentor/progress", headers=bob["headers"]).json() == {
        "lessons_viewed": [], "quiz": {"attempts": 0, "best_score": None}, "challenges_passed": [],
    }
