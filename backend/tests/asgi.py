"""Minimal raw ASGI caller: lets tests control body chunking, Content-Length and the client address."""
import json
from dataclasses import dataclass, field


@dataclass
class Result:
    status: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    receive_calls: int = 0

    def json(self):
        return json.loads(self.body)


async def call(app, method, path, *, headers=(), chunks=(b"",), client=("203.0.113.5", 40000),
               content_length="auto", disconnect_after=None) -> Result:
    """Send one request. `chunks` are delivered as separate http.request messages.

    content_length: "auto" (sum of chunks), an int/str to declare, or None to omit the header.
    disconnect_after: deliver this many chunks, then http.disconnect instead of the rest.
    """
    hdrs = [(k.lower().encode(), v.encode("latin-1")) for k, v in headers]
    if content_length == "auto":
        total = sum(len(c) for c in chunks)
        if total:
            hdrs.append((b"content-length", str(total).encode()))
    elif content_length is not None:
        hdrs.append((b"content-length", str(content_length).encode()))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": b"", "headers": hdrs,
             "client": client, "server": ("test", 80)}
    result = Result()
    queue = list(chunks)
    delivered = 0

    async def receive():
        nonlocal delivered
        result.receive_calls += 1
        if disconnect_after is not None and delivered >= disconnect_after:
            return {"type": "http.disconnect"}
        if queue:
            chunk = queue.pop(0)
            delivered += 1
            return {"type": "http.request", "body": chunk, "more_body": bool(queue)}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            result.status = message["status"]
            result.headers = {k.decode().lower(): v.decode() for k, v in message["headers"]}
        elif message["type"] == "http.response.body":
            result.body += message.get("body", b"")

    await app(scope, receive, send)
    return result
