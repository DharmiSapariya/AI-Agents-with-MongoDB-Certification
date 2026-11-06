"""Agent One loop driven by a scripted fake LLM.

These tests exercise the real LangGraph wiring, routing and tracer, but use mongomock,
an in-memory checkpointer and a fake model. They do not prove Atlas, Vector Search or
OpenAI integration works.
"""
import sys
from types import SimpleNamespace

import mongomock
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from app import graph, tools


class ScriptedModel(BaseChatModel):
    replies: list = []

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, *_, **__):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])


def tool_call(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


@pytest.fixture
def agent(monkeypatch):
    database = mongomock.MongoClient()["t"]
    database["full_docs"].insert_one({"title": "Aggregation", "body": "pipeline stages"})
    model = ScriptedModel()
    monkeypatch.setattr(graph, "db", lambda: database)
    monkeypatch.setattr(tools, "db", lambda: database)
    monkeypatch.setattr(graph, "client", lambda: None)
    monkeypatch.setattr(graph, "MongoDBSaver", lambda *a, **k: MemorySaver())
    monkeypatch.setattr(graph, "_app", None)
    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=lambda **k: model))
    return model, database


def events(database, thread_id):
    return list(database["agent_execution_events"].find({"thread_id": thread_id}).sort("seq"))


def test_tool_call_then_answer_is_traced(agent):
    model, database = agent
    model.replies = [tool_call("get_page_content_for_summarization", {"user_query": "Aggregation"}),
                     AIMessage(content="Summary.")]
    result = graph.run("t1", "summarize Aggregation")
    assert result["answer"] == "Summary." and result["fully_recorded"]
    kinds = [e["type"] for e in events(database, "t1")]
    assert kinds == ["execution_start", "agent_decision", "tool_start", "db_operation",
                     "tool_end", "agent_decision", "execution_end"]


def test_runaway_tool_loop_stops_at_recursion_limit(agent):
    model, database = agent
    model.replies = [tool_call("get_page_content_for_summarization", {"user_query": "Aggregation"}, str(i))
                     for i in range(40)]
    with pytest.raises(Exception, match="Recursion limit"):
        graph.run("t2", "loop")
    last = events(database, "t2")[-1]
    assert last["type"] == "execution_end" and last["data"]["status"] == "error"


def test_unknown_tool_is_recorded_as_error_not_executed(agent):
    model, database = agent
    model.replies = [tool_call("drop_database", {}), AIMessage(content="done")]
    graph.run("t3", "x")
    ends = [e for e in events(database, "t3") if e["type"] == "tool_end"]
    assert ends[0]["data"]["status"] == "error"


def test_threads_do_not_share_events(agent):
    model, database = agent
    model.replies = [AIMessage(content="a"), AIMessage(content="b")]
    graph.run("one", "q1")
    graph.run("two", "q2")
    assert {e["thread_id"] for e in events(database, "one")} == {"one"}
    assert {e["thread_id"] for e in events(database, "two")} == {"two"}
