import io
import json
import logging

import pytest

from app.logging_config import JsonFormatter, configure_logging, execution_id_var, log, request_id_var
from app.tracing import redact


@pytest.fixture
def stream():
    buf = io.StringIO()
    logger = logging.getLogger("app.test_logging")
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter(["internal-[a-z0-9]+"]))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    yield logger, buf
    logger.removeHandler(handler)


def last(buf):
    return json.loads(buf.getvalue().strip().splitlines()[-1])


def test_line_is_json_with_standard_fields(stream):
    logger, buf = stream
    log(logger, logging.INFO, "tool_finished", tool="search", duration_ms=12.5, returned=3)
    row = last(buf)
    assert row["event"] == "tool_finished" and row["level"] == "INFO" and row["logger"] == "app.test_logging"
    assert row["duration_ms"] == 12.5 and row["returned"] == 3
    assert row["ts"].endswith("+00:00") and "T" in row["ts"]


def test_request_and_execution_ids_are_attached_when_set(stream):
    logger, buf = stream
    log(logger, logging.INFO, "no_ids")
    assert "request_id" not in last(buf)
    r, e = request_id_var.set("req-123"), execution_id_var.set("exec-456")
    try:
        log(logger, logging.INFO, "with_ids")
    finally:
        request_id_var.reset(r)
        execution_id_var.reset(e)
    assert last(buf)["request_id"] == "req-123" and last(buf)["execution_id"] == "exec-456"


def test_secrets_are_redacted_in_message_and_fields(stream):
    logger, buf = stream
    logger.info("connecting to mongodb+srv://u:hunter2@h.example.net/db with key sk-abcdefghijklmnop")
    log(logger, logging.INFO, "headers", authorization="Bearer abc.def.ghi", note="see internal-xyz99 and password=hunter2")
    first, second = buf.getvalue().strip().splitlines()
    assert "hunter2" not in first and "sk-abcdefghijklmnop" not in first
    row = json.loads(second)
    assert row["authorization"] == "[REDACTED]"
    assert "internal-xyz99" not in row["note"] and "hunter2" not in row["note"]


def test_bearer_tokens_in_free_text_are_redacted():
    assert "abc.def" not in redact("Authorization: Bearer abc.def.ghi")


def test_exception_is_logged_with_type_and_redacted_traceback(stream):
    logger, buf = stream
    try:
        raise RuntimeError("cannot reach mongodb+srv://u:hunter2@h.example.net/db")
    except RuntimeError:
        logger.exception("request_failed")
    row = last(buf)
    assert row["exc_type"] == "RuntimeError"
    assert "hunter2" not in json.dumps(row)
    assert "RuntimeError" in row["traceback"]


def test_configure_logging_is_idempotent():
    configure_logging("INFO")
    configure_logging("DEBUG", ["x-[0-9]+"])
    app_logger = logging.getLogger("app")
    assert len([h for h in app_logger.handlers if getattr(h, "_app_json_handler", False)]) == 1
    assert app_logger.level == logging.DEBUG and app_logger.propagate is False
