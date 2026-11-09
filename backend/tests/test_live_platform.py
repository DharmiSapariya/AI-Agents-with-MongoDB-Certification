"""Opt-in integration checks for an isolated Atlas corpus and model account."""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import graph, mongo
from app.config import settings
from app.main import app
from app.retrieval import index_state, vector_search
from app.tools import generate_embedding, get_page_content_for_summarization

TITLE = "compound-index-prefix"
SOURCE = f"{TITLE}.md"
QUESTION = "Can I use the first field of a compound index by itself?"

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_PLATFORM_TESTS") != "1",
    reason="Opt in with RUN_LIVE_PLATFORM_TESTS=1 on dedicated Atlas databases.",
)


def test_live_platform_round_trip(monkeypatch):
    # The app writes accounts, sessions, traces, and checkpoints during this test.
    assert settings.db_name.startswith("agent_verify_"), "Use a dedicated agent_verify_ corpus database."
    assert settings.checkpoint_db.startswith("agent_verify_"), "Use a dedicated agent_verify_ checkpoint database."
    assert settings.db_name != settings.checkpoint_db
    assert settings.app_mode == "live" and settings.configured and settings.auth_enabled

    monkeypatch.setattr(graph, "_app", None)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["mongodb"] == "connected"

        chunks = mongo.db()["chunked_docs"]
        assert index_state(chunks, settings) == "ready"
        vector = generate_embedding(QUESTION)
        assert len(vector) == settings.embedding_dims
        rows = vector_search(chunks, settings, vector)
        assert SOURCE in [row.get("source") for row in rows]
        full_page = get_page_content_for_summarization.invoke({"user_query": TITLE})
        assert "<retrieved_document" in full_page

        account = {"email": f"release-{uuid4().hex}@example.com", "password": uuid4().hex}
        assert client.post("/api/auth/register", json=account).status_code == 201
        login = client.post("/api/auth/login", json=account)
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = client.post("/api/chat", headers=headers, json={"message": f"Summarize the page titled {TITLE}."})
        assert response.status_code == 200
        result = response.json()
        assert result["outcome"] == "answered"
        assert any(citation.get("source") == SOURCE for citation in result["citations"])
        session_id, execution_id = result["session_id"], result["execution_id"]
        execution = client.get(f"/api/executions/{execution_id}", headers=headers)
        assert execution.status_code == 200
        assert any(event["type"] == "db_operation" for event in execution.json())
        mentor = client.post("/api/mentor/run", headers=headers, json={"mode": "watch", "execution_id": execution_id})
        assert mentor.status_code == 200 and mentor.json()["steps"]

    # Rebuild the application graph after closing and reopening its MongoDB client.
    monkeypatch.setattr(graph, "_app", None)
    with TestClient(app) as restarted:
        compiled = graph.build_app()
        checkpoint = compiled.get_state({"configurable": {"thread_id": session_id}})
        assert checkpoint.values.get("messages"), "The new graph did not restore the conversation."
        history = restarted.get(f"/api/sessions/{session_id}/history", headers=headers)
        assert history.status_code == 200
        assert history.json()[0]["execution_id"] == execution_id
