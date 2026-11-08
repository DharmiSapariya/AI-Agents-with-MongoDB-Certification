# Architecture decisions

Status per record: Accepted (already true in code) or Proposed (to be confirmed when implemented).

## 1. Keep the course architecture (Accepted)
Two tools (`get_information_for_question_answering`, `get_page_content_for_summarization`), collections `chunked_docs` and `full_docs`, a two-node LangGraph loop, and `MongoDBSaver` for checkpoints. Extensions (tracing, auth, memory) are added around it, not in place of it. Anything beyond the course is labelled as such in docs.

## 2. No silent vector-search fallback (Accepted)
If `$vectorSearch` fails (index missing or not ready, Atlas unreachable), the tool returns an error that is recorded in the trace. It never substitutes keyword search.

## 3. Redaction at write time (Accepted)
`tracing.redact` runs before events are stored. Only observable actions are recorded, never model reasoning.

## 4. Authentication and ownership (Accepted, sessions 4 and 6)
Email and password accounts in a `users` collection (password hashed with a standard KDF), short-lived signed access tokens. Every thread is stored in `agent_sessions` with `user_id`; the checkpoint `thread_id` is generated server-side, never taken from the client, and every route resolves it through that ownership record. Events, memories and mentor sessions carry `user_id` and are always queried with it. Chosen over a shared API key because the requirement is per-user isolation, which a shared key cannot give. Rate limiting is applied per user and per IP.

## 5. Three memory layers kept separate (Proposed)
Graph checkpoints (MongoDBSaver, owned by LangGraph, not edited by us); conversation history (derived from checkpoint state for display); long-term memory (own `agent_memory` collection, written only after explicit user approval, deletable). Memory is retrieved text; model weights never change.

## 6. Mentor is a separate LangGraph graph (Proposed)
Own prompt, routes, sessions and tracing (`agent` = "mentor"). Its tools are read-only and scoped to the requesting user's sanitized primary-agent events. It cannot write to primary-agent collections. The existing rule-based explainer stays as deterministic fallback content and is labelled as such.

## 7. Frontend replaces `index.html` only when the React app can do what it does (Proposed)
Vite + React + TypeScript in `frontend/`. The static page remains until the playground and mentor pages work against the real API.

## 8. Dependency pinning (Proposed)
Pin to versions that were installed and the tests run against, recorded in a lock file. langchain-openai and voyageai are pinned only after being installed and imported in CI.

## 9. Three run modes, validated at startup (Accepted, session 3)
`APP_MODE` is `auto`, `demo` or `live`. `auto` keeps the earlier behaviour (live only when all three credentials exist) so existing `.env` files still work; `live` is for deployments and fails at startup when anything is missing; `demo` never contacts services. Partial credentials in `auto` mode stay demo and `/health` lists the missing variable names. Validation errors name variables, never values, because pydantic's default messages echo the input.

## 10. Start even if Atlas is down (Accepted, session 3)
PyMongo connects lazily, and the lifespan only creates the client and logs a startup check. If Atlas is unreachable the app still starts, `/health` returns 503 in live mode with `mongodb: unreachable`, and requests fail with `database_unavailable`. Chosen over crashing at startup so an orchestrator sees a running but degraded service and a transient Atlas outage does not cause a restart loop. Revisit if a deployment target prefers fail-fast.

## 11. Request IDs in pure ASGI middleware (Accepted, session 3)
The ID lives in a `ContextVar` set before routing, so it reaches worker threads (FastAPI copies context) and is isolated per request. The middleware also turns unhandled exceptions into the standard 500 body so the `X-Request-ID` header is present on failures; Starlette's own 500 handler runs outside user middleware and would omit it.

## 12. Database access through a lazy provider dependency (Accepted, session 3)
Read routes receive a callable (`db_provider`) and call it after their config and allowlist checks. Passing the database itself made a missing database mask 403/422 responses. Tests override `db_provider` with a mongomock database; non-route code uses `mongo.set_client()`.

## 13. Error classification by exception type and cause chain (Accepted, session 3)
`errors.classify` maps PyMongo, OpenAI, Voyage, LangGraph and timeout exceptions to stable codes and HTTP statuses, following `__cause__`/`__context__` so wrapped failures keep their category. Only the code and a fixed message reach clients. Limitation: classification relies on SDK exception classes that tests construct by hand; real provider failures have not been observed.

## 14. Account and token design (Accepted, session 4)
- **Libraries:** `argon2-cffi` (Argon2id, library defaults: 64 MiB, 3 passes, 4 lanes) and `PyJWT` (HS256). A shared secret is enough because one service both issues and verifies tokens; switch to RS256/EdDSA if another service must verify.
- **Email:** ASCII-only, trimmed and lowercased. Non-ASCII is rejected rather than folded because `str.lower()` maps characters such as the Kelvin sign to ASCII letters, which would let look-alike addresses collide.
- **Uniqueness:** a unique index on `users.email`; registration inserts and catches `DuplicateKeyError` instead of checking first, so concurrent registrations cannot both succeed. `create_user` also calls the idempotent `create_index` so a missed startup step cannot leave the index absent.
- **Equal login cost:** unknown email, malformed email and wrong password each run one Argon2 verification (unknown emails verify against a precomputed `DUMMY_HASH`). A first version computed the dummy hash lazily and measured about 2x slower for unknown users; the constant removed that. A test checks the constant still matches the hasher's parameters.
- **Event loop:** routes are plain `def`, so FastAPI runs hashing and PyMongo calls in its threadpool. A semaphore (`AUTH_MAX_CONCURRENT_HASHES`) bounds concurrent 64 MiB hashes until item 7 adds request limits.
- **Availability:** auth is enabled outside demo mode when `MONGODB_URI` and `JWT_SECRET` are set. `APP_MODE=live` requires `JWT_SECRET`. In `auto` mode a missing secret does not turn a working live config into demo; the auth routes return 503 and `/health` reports `auth: unavailable`. Item 6 will make protected routes depend on this.
- **Not included:** refresh tokens, revocation (a token is valid until `exp` while the user exists), password reset, email verification, OAuth. Deleting a user invalidates their tokens because every request reloads the user.

## 15. Session ownership (Accepted, session 6)
- **Identity comes only from the verified token.** The chat body forbids extra fields, so a client-supplied `thread_id` or `user_id` is a 422 rather than silently ignored; headers such as `X-User-Id` have no effect (tested).
- **Session ids** are `s_` plus 128 random bits, generated in `sessions.create`. The LangGraph `thread_id` is that id, so checkpoints are only ever keyed by an id the server issued, and only after `get_owned` succeeded.
- **404 for both missing and foreign** sessions and executions, with identical bodies apart from the request id, so ids cannot be probed. A format error (`bad id`) is 400 and reveals nothing about existence.
- **Every owner-scoped query includes `user_id`**, including list, detail, Mentor explain and the explorer. Tracer events carry `user_id`; `None` marks legacy events, which match no query.
- **Explorer** is a fixed table (collection, owned or shared, returned fields) with bounded `limit` and `skip`. Shared knowledge collections hide `body` and `embedding`; the `users` and checkpoint collections are unreachable.
- **Public health** drops exception type names and missing variable names (still logged), since the endpoint is unauthenticated.
- **Quiz grading** needs a token when accounts are enabled and stays anonymous in demo mode, where no account store exists.
- **Known gap:** an expected 4xx/5xx raised deliberately (for example `demo_mode`, `auth_unavailable`) is logged with a traceback at ERROR. Under abusive traffic that is noisy; roadmap item 7 will bound it.
