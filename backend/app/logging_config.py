"""JSON logging with request/execution correlation and secret redaction.

Log the event and operational facts (ids, counts, durations, error categories). Do not log
prompts, answers or retrieved text: they can contain personal data.
"""
import json
import logging
import re
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

from .context import execution_id_var, request_id_var
from .tracing import redact

_HANDLER_FLAG = "_app_json_handler"


class JsonFormatter(logging.Formatter):
    def __init__(self, extra_patterns: list[str] | None = None):
        super().__init__()
        self.patterns = [re.compile(p) for p in extra_patterns or []]

    def _clean(self, value: Any) -> Any:
        return redact(value, self.patterns)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": self._clean(record.getMessage()),
        }
        if (request_id := request_id_var.get()) is not None:
            payload["request_id"] = request_id
        if (execution_id := execution_id_var.get()) is not None:
            payload["execution_id"] = execution_id
        payload.update(self._clean(getattr(record, "fields", {})))
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            payload["exc_type"] = type(exc).__name__
            payload["exc_message"] = self._clean(str(exc))
            payload["traceback"] = self._clean("".join(traceback.format_exception(*record.exc_info)))
        return json.dumps(payload, default=str)


def log(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit a structured event; fields become top-level keys in the JSON line."""
    logger.log(level, event, extra={"fields": fields})


def configure_logging(level: str = "INFO", extra_patterns: list[str] | None = None) -> None:
    """Route the `app` logger tree to stdout as JSON. Safe to call more than once."""
    root = logging.getLogger("app")
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_FLAG, False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    setattr(handler, _HANDLER_FLAG, True)
    handler.setFormatter(JsonFormatter(extra_patterns))
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    logging.getLogger("uvicorn.access").disabled = True  # request_completed events replace it
