from types import SimpleNamespace

from app import mentor
from app.routing import END, route_tools
from app.tracing import Tracer, redact


class FakeCol:
    def __init__(self, fail=False):
        self.docs, self.fail = [], fail

    def insert_one(self, d):
        if self.fail:
            raise RuntimeError("down")
        self.docs.append(d)


def test_redaction():
    out = redact({"mongodb_uri": "x", "t": "mongodb+srv://u:p@h/db and sk-abcdefghijkl1234"})
    assert out["mongodb_uri"] == "[REDACTED]"
    assert "u:p@h" not in out["t"] and "sk-abc" not in out["t"]


def test_router():
    tc = SimpleNamespace(tool_calls=[{"name": "x"}])
    assert route_tools({"messages": [tc]}) == "tools"
    assert route_tools({"messages": [SimpleNamespace(tool_calls=[])]}) == END


def test_tracer_records_and_flags_failures():
    col = FakeCol()
    t = Tracer(col, "th", "primary", "hi")
    t.emit("tool_start", tool="a")
    t.finish("success", "ok")
    assert [d["seq"] for d in col.docs] == [1, 2, 3] and t.recorded_ok
    bad = Tracer(FakeCol(fail=True), "th", "primary", "hi")
    bad.finish("success")
    assert not bad.recorded_ok


def test_mentor_separates_recorded_from_interpretation():
    evs = [{"seq": 1, "type": "agent_decision", "node": "agent",
            "data": {"tool_calls": [{"name": "get_page_content_for_summarization", "args": {}}]}}]
    step = mentor.explain_execution(evs)["steps"][0]
    assert "recorded" in step and "interpretation" in step
    assert "get_page_content_for_summarization" in step["interpretation"]


def test_quiz_grading():
    r = mentor.grade({"q1": 1, "q2": 0, "q3": 0})
    assert r["score"] == 2 and r["total"] == 3
