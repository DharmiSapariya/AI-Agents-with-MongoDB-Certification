# Architecture decisions

Status per record: Accepted (already true in code) or Proposed (to be confirmed when implemented).

## 1. Keep the course architecture (Accepted)
Two tools (`get_information_for_question_answering`, `get_page_content_for_summarization`), collections `chunked_docs` and `full_docs`, a two-node LangGraph loop, and `MongoDBSaver` for checkpoints. Extensions (tracing, auth, memory) are added around it, not in place of it. Anything beyond the course is labelled as such in docs.

## 2. No silent vector-search fallback (Accepted)
If `$vectorSearch` fails (index missing or not ready, Atlas unreachable), the tool returns an error that is recorded in the trace. It never substitutes keyword search.

## 3. Redaction at write time (Accepted)
`tracing.redact` runs before events are stored. Only observable actions are recorded, never model reasoning.

## 4. Authentication and ownership (Proposed)
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
