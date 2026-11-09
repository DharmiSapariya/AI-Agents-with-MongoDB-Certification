# Session handoff

**Roadmap item 7 (abuse limits and request size caps).** Base `858d204` (origin/main; item 6 confirmed there). Branch `session6-abuse-limits` holds one commit: `feat(security): add rate limits and request size protections`. Not pushed. READY TO PUBLISH.

Checks (clean venv, Python 3.12): `pytest -q` 238 passed (baseline at 858d204: 174); `ruff check . ../scripts` clean; `mypy app` clean (23 files); `git diff --check` clean. Mocked: fake clock, mongomock, fake graph. Real uvicorn smoke in demo mode: normal 200, 429 with `Retry-After`, 413 for a declared and a chunked oversized body, `/health` exempt, matching request ids, one throttled log line per category. Mutation checks: IP check off -> 22 failures, chunk counting off -> 2, user budget off -> 7. Not run: Atlas, providers, GitHub CI, a reverse proxy, several workers.

Decisions to keep: ADR 16 (token bucket, process-local; limits in middleware inside request-id and CORS; per-user chat budget after auth and before the ownership lookup; body buffered up to the cap and replayed; client address only from `scope["client"]`; expected errors logged once per interval without tracebacks). Rate limits do not apply to `/health`; `RATE_LIMIT_ENABLED=false` keeps body caps. Tests: `tests/conftest.py` resets `app.state.limits` and the log throttle before every test; use `tests/clock.py` and `tests/asgi.py` for deterministic time and raw ASGI bodies.

Existing tests changed: `test_concurrent_registration_of_one_email_creates_one_account` now raises the per-IP registration limit (12 requests exceed the new default of 10/hour); it is about the unique index.

Remaining limitations: counters are per process (N workers ~ N x budget, reset on restart); no body read timeout; proxy topology untested; a provider-backed Mentor mode does not exist and must get a user budget when added.

**Next: roadmap item 8**, the exhaustive cross-user and abuse regression matrix. First actions: list every route in the README and docs tables; build one parametrized test matrix over (route x {anonymous, user A, user B accessing A's resource, expired token, legacy unowned data}) asserting status, error code and that no data from the other user appears; add stream-establishment cases only if a streaming route exists (it does not yet); keep mongomock and real-MongoDB variants distinguishable (live tests opt-in).

Needs from the user: Atlas URI with a vector index, OpenAI and Voyage keys, `JWT_SECRET` for live runs.
