"""Agent Two: MongoDB Agent Mentor.

Independent of Agent One: own collections (quiz_attempts), own content, own endpoints.
It only READS recorded events and never writes to Agent One's data.
Every explanation separates RECORDED facts from INTERPRETATION.
"""
from datetime import datetime, timezone
from typing import Any

CONCEPTS = {
    "agent": {"official": True, "title": "What is an AI agent?",
              "text": "A software system that can reason about a scenario, use tools, and keep memory. "
                      "Unlike a fixed pipeline, it decides which step to take next."},
    "tools": {"official": True, "title": "Tools and function calling",
              "text": "Tools are functions the LLM can request. The LLM emits a structured call (name + arguments); "
                      "your code executes it and returns the result to the LLM."},
    "langgraph": {"official": True, "title": "LangGraph: state, nodes, edges",
                  "text": "State is a shared snapshot (here: a list of messages with an append reducer). Nodes update state; "
                          "edges connect them; a conditional edge routes to 'tools' or END, creating the agent loop."},
    "memory": {"official": True, "title": "Short-term vs long-term memory",
               "text": "Short-term memory = conversation state saved per thread_id via the MongoDB checkpointer. "
                       "Long-term memory = information stored across sessions. The model's weights never change; "
                       "memory is retrieved stored data."},
    "vector_search": {"official": True, "title": "Embeddings and vector search",
                      "text": "Text is converted to vectors; $vectorSearch returns chunks whose vectors are closest "
                              "(cosine) to the query vector."},
    "observability": {"official": False, "title": "Agent observability (additional material)",
                      "text": "This project records each graph/tool/database event in MongoDB so executions can be inspected."},
}

QUIZ: list[dict[str, Any]] = [
    {"id": "q1", "q": "Which tool handles 'Summarize the aggregation page'?",
     "options": ["get_information_for_question_answering", "get_page_content_for_summarization"], "answer": 1,
     "why": "Summaries need the full page, fetched by exact title with find_one on full_docs."},
    {"id": "q2", "q": "What identifies a conversation for the MongoDB checkpointer?",
     "options": ["thread_id", "embedding", "index name"], "answer": 0,
     "why": "The checkpointer loads state saved under the same thread_id."},
    {"id": "q3", "q": "What does the add_messages reducer do?",
     "options": ["Replaces the messages list", "Appends new messages to history"], "answer": 1,
     "why": "Without a reducer a key is overwritten; add_messages appends."},
]


_LESSON_FILES = {
    "agent": "backend/app/graph.py",
    "tools": "backend/app/tools.py",
    "langgraph": "backend/app/routing.py",
    "memory": "backend/app/memory.py",
    "vector_search": "backend/app/retrieval.py",
    "observability": "backend/app/tracing.py",
}

CHALLENGES = {
    "trace-routing": {"title": "Follow the routing decision",
                      "task": "Inspect route_tools and identify what sends a run to the tools node.",
                      "options": ["A pending tool call", "A saved note", "An empty trace"],
                      "answer": 0, "file": "backend/app/routing.py"},
    "memory-scope": {"title": "Find the memory ownership guard",
                     "task": "Inspect list_owned and identify what scopes the lookup.",
                     "options": ["Client IP", "Verified account user ID", "Lesson title"],
                     "answer": 1, "file": "backend/app/memory.py"},
}


def challenge(challenge_id: str, choice: int) -> dict:
    item = CHALLENGES[challenge_id]
    return {"challenge_id": challenge_id, "passed": choice == item["answer"],
            "file": item["file"]}


def teach(concept: str) -> dict | None:
    lesson = CONCEPTS.get(concept)
    if lesson is None:
        return None
    return {**lesson, "file": _LESSON_FILES[concept],
            "exercise": f"Open {_LESSON_FILES[concept]} and trace where the lesson concept appears."}


def grade(answers: dict[str, int]) -> dict:
    results, score = [], 0
    for q in QUIZ:
        ok = answers.get(q["id"]) == q["answer"]
        score += ok
        results.append({"id": q["id"], "correct": ok, "why": q["why"]})
    return {"score": score, "total": len(QUIZ), "results": results,
            "at": datetime.now(timezone.utc).isoformat()}


def explain_execution(events: list[dict]) -> dict:
    """Turn recorded events into steps: {recorded: <event data>, interpretation: <text>}."""
    steps = []
    for ev in sorted(events, key=lambda e: e["seq"]):
        t, d = ev["type"], ev.get("data", {})
        if t == "execution_start":
            note = "The user's question started a new graph run."
        elif t == "agent_decision" and d.get("tool_calls"):
            names = ", ".join(c["name"] for c in d["tool_calls"])
            note = (f"The LLM requested tool(s): {names}. Routing sent the run to the tools node because the last "
                    "message contained tool calls. (Why the model chose it is not recorded; only the choice is.)")
        elif t == "agent_decision":
            note = "The LLM returned no tool calls, so the conditional edge routed to END with a final answer."
        elif t == "tool_start":
            note = f"Tool '{d.get('tool')}' started."
        elif t == "db_operation":
            note = (f"MongoDB operation {d.get('op')} on '{d.get('collection')}' returned {d.get('returned')} "
                    "document(s); this is the evidence the LLM could use next.")
        elif t == "tool_end":
            note = f"Tool finished with status '{d.get('status')}'; its result was appended to state as a ToolMessage."
        elif t == "error":
            note = "The run failed; see the recorded error."
        elif t == "execution_end":
            note = (f"Run ended with status '{d.get('status')}'. "
                    + ("All events were persisted." if d.get("fully_recorded") else
                       "WARNING: some events failed to persist; this trace is incomplete."))
        else:
            note = "Event recorded."
        steps.append({"seq": ev["seq"], "type": t, "node": ev.get("node"),
                      "recorded": d, "interpretation": note})
    return {"steps": steps, "disclaimer": "'recorded' is actual stored data; 'interpretation' is explanatory text."}
