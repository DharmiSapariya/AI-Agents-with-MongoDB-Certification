"""JSON logging with request/execution correlation and secret redaction.

Log the event and operational facts (ids, counts, durations, error categories). Do not log
prompts, answers or retrieved text: they can contain personal data.
"""
import json
import logging
import re
import sys
import threading
import time
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


class EventThrottle:
    """Allow one log line per key per interval; the next allowed line reports how many were skipped."""

    def __init__(self, interval_s: float, clock=time.monotonic, max_keys: int = 256):
        self.interval_s = interval_s
        self._clock = clock
        self._max_keys = max_keys
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}
        self._skipped: dict[str, int] = {}

    def allow(self, key: str) -> int | None:
        """None means suppress; otherwise the number of lines suppressed since the last one."""
        now = self._clock()
        with self._lock:
            last = self._last.get(key)
            if last is not None and now - last < self.interval_s:
                self._skipped[key] = self._skipped.get(key, 0) + 1
                return None
            if last is None and len(self._last) >= self._max_keys:
                return None  # category names are fixed in code, so this is a safety bound only
            self._last[key] = now
            return self._skipped.pop(key, 0)


_throttle = EventThrottle(10)


def set_throttle(throttle: EventThrottle) -> EventThrottle:
    """Install a throttle (startup config, tests); returns the previous one."""
    global _throttle
    previous, _throttle = _throttle, throttle
    return previous


def log_expected(logger: logging.Logger, level: int, event: str, category: str, **fields: Any) -> None:
    """Log an expected rejection (limits, 401/404/503 on purpose) at most once per interval per category."""
    fields.pop("error_category", None)
    suppressed = _throttle.allow(f"{event}:{category}")
    if suppressed is None:
        return
    if suppressed:
        fields["suppressed_since_last"] = suppressed
    log(logger, level, event, error_category=category, **fields)


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
