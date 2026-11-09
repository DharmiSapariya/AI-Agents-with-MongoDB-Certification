import json

from app import graph
from app.context import request_id_var
from app.protection import Limits
from app.tracing import Tracer


def frames(response):
    return [(name.removeprefix("event: "), json.loads(data.removeprefix("data: ")))
            for name, data in (frame.splitlines() for frame in response.text.strip().split("\n\n"))]


def test_stream_sends_safe_ordered_trace_and_final_result(two_users, monkeypatch):
    client, database, alice, _ = two_users

    def run(session_id, message, user_id, on_event):
        tracer = Tracer(database.agent_execution_events, session_id, "primary", message,
                        user_id=user_id, on_event=on_event)
        tracer.emit("tool_start", node="tools", args={"private": "not-for-stream"})
        tracer.finish("success", "answer")
        return {"answer": "answer", "execution_id": tracer.execution_id, "citations": []}

    monkeypatch.setattr(graph, "run", run)
    response = client.post("/api/chat/stream", headers={**alice["headers"], "X-Request-ID": "stream-1"},
                           json={"message": "private-prompt"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = frames(response)
    assert [kind for kind, _ in events] == ["session", "trace", "trace", "trace", "result"]
    assert [body["seq"] for kind, body in events if kind == "trace"] == [1, 2, 3]
    assert all(body["request_id"] == "stream-1" for _, body in events)
    assert "private-prompt" not in response.text
    assert "not-for-stream" not in response.text
    result = events[-1][1]
    assert result["answer"] == "answer"
    assert database.sessions.find_one({"_id": result["session_id"]})["turns"] == 1


def test_stream_fails_with_a_terminal_error_and_no_completed_turn(two_users, monkeypatch):
    client, database, alice, _ = two_users

    def run(*args, **kwargs):
        assert request_id_var.get() == "stream-failure"
        raise TimeoutError("provider-private-detail")

    monkeypatch.setattr(graph, "run", run)
    response = client.post("/api/chat/stream", headers={**alice["headers"], "X-Request-ID": "stream-failure"},
                           json={"message": "question"})
    events = frames(response)
    assert [kind for kind, _ in events] == ["session", "failed"]
    error = events[-1][1]["error"]
    assert error["code"] == "timeout" and error["request_id"] == "stream-failure"
    assert "provider-private-detail" not in response.text
    assert database.sessions.find_one()["turns"] == 0


def test_stream_and_json_share_chat_ip_budget(two_users, monkeypatch):
    from clock import Clock

    from app.config import settings
    from app.main import app

    limits = settings.model_copy(update={"rate_chat_ip_per_min": 1})
    monkeypatch.setattr(app.state, "limits", Limits.from_settings(limits, Clock()))
    client, _, _, _ = two_users
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401
    response = client.post("/api/chat/stream", json={"message": "hi"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
