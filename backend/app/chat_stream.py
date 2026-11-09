"""Server-sent execution events for a single accepted chat turn."""
import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress

from typing_extensions import Unpack

from . import sessions
from .context import request_id_var
from .errors import classify, error_body
from .memory import MemoryOptions


def _frame(kind: str, payload: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(payload)}\n\n"


async def stream_turn(database, session_id: str, message: str, user_id: str,
                      **options: Unpack[MemoryOptions]) -> AsyncIterator[str]:
    from .graph import run

    loop = asyncio.get_running_loop()
    pending: asyncio.Queue[tuple[str, dict]] = asyncio.Queue(maxsize=32)
    execution_id = None

    def publish(event: dict) -> None:
        nonlocal execution_id
        execution_id = event["execution_id"]

        def enqueue() -> None:
            with suppress(asyncio.QueueFull):
                pending.put_nowait(("trace", event))

        with suppress(RuntimeError):  # the server loop can close after a disconnect
            loop.call_soon_threadsafe(enqueue)

    def execute() -> dict:
        result = run(session_id, message, user_id=user_id, on_event=publish, **options)
        sessions.record_turn(database, session_id)
        return result

    async def produce() -> None:
        try:
            result = await asyncio.to_thread(execute)
        except Exception as exc:
            error = classify(exc)
            await pending.put(("failed", {**error_body(error.code, error.message), "execution_id": execution_id}))
        else:
            await pending.put(("result", {**result, "session_id": session_id, "request_id": request_id_var.get()}))

    yield _frame("session", {"session_id": session_id, "request_id": request_id_var.get()})
    worker = asyncio.create_task(produce())
    try:
        while True:
            kind, payload = await pending.get()
            yield _frame(kind, payload)
            if kind != "trace":
                break
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
