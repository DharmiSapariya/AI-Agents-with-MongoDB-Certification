"""Persistent execution tracing. Records observable events only (no chain-of-thought)."""
import re
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Sequence

from .context import request_id_var

SECRET_RE = re.compile(
    r"(mongodb(\+srv)?://[^\s\"']+|sk-[A-Za-z0-9_\-]{10,}|pa-[A-Za-z0-9_\-]{10,}"
    r"|bearer\s+[A-Za-z0-9._~+/\-]+=*"
    r"|(api[_-]?key|token|password)\s*[=:]\s*\S+)", re.I)
SENSITIVE_KEYS = {"api_key", "openai_api_key", "voyage_api_key", "password", "token", "mongodb_uri",
                  "authorization", "cookie", "set-cookie", "secret"}


def redact(value: Any, extra_patterns: Sequence[re.Pattern] = ()) -> Any:
    """Recursively mask secrets in strings and sensitive dict keys.

    extra_patterns are additional compiled regexes whose matches are masked in strings.
    """
    if isinstance(value, str):
        value = SECRET_RE.sub("[REDACTED]", value)
        for pattern in extra_patterns:
            value = pattern.sub("[REDACTED]", value)
        return value
    if isinstance(value, dict):
        return {k: "[REDACTED]" if str(k).lower() in SENSITIVE_KEYS else redact(v, extra_patterns)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, extra_patterns) for v in value]
    return value


class Tracer:
    """Writes one document per event to `agent_execution_events`."""

    def __init__(self, collection, thread_id: str, agent: str, user_input: str, model: str = ""):
        self.col = collection
        self.execution_id = uuid.uuid4().hex
        self.thread_id = thread_id
        self.agent = agent
        self.seq = 0
        self.t0 = time.perf_counter()
        self.recorded_ok = True
        self.errors: list[str] = []
        self.emit("execution_start", node="START", user_input=user_input, model=model)

    def emit(self, type_: str, node: str | None = None, **data: Any) -> dict:
        self.seq += 1
        doc = {
            "execution_id": self.execution_id, "thread_id": self.thread_id, "agent": self.agent,
            "seq": self.seq, "type": type_, "node": node, "request_id": request_id_var.get(),
            "ts": datetime.now(timezone.utc), "data": redact(data),
        }
        try:
            self.col.insert_one(dict(doc))
        except Exception as exc:  # never claim full recording if a write failed
            self.recorded_ok = False
            self.errors.append(f"{type(exc).__name__}: {exc}")
        return doc

    def finish(self, status: str, final_answer: str = "") -> None:
        self.emit("execution_end", node="END", status=status,
                  duration_ms=round((time.perf_counter() - self.t0) * 1000, 1),
                  final_answer=final_answer, fully_recorded=self.recorded_ok)


CURRENT: ContextVar[Tracer | None] = ContextVar("current_tracer", default=None)


def emit(type_: str, node: str | None = None, **data: Any) -> None:
    t = CURRENT.get()
    if t:
        t.emit(type_, node=node, **data)
