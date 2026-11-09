# Implementation status

See the [release evidence](RELEASE_EVIDENCE.md) for the latest verification
and the [roadmap](DEVELOPMENT_ROADMAP.md) for milestone history.
Local tests with mongomock, scripted providers, or an in-memory checkpointer
are separate from live-provider verification.

## Core route policy
Scope: **public**, **auth** (any signed-in user; 503 `demo_mode` first when not live), **owner** (auth and every query filtered by the token's user id; foreign and missing both 404).

| Route | Scope | Notes |
|---|---|---|
| `GET /health`, `GET /` | public | health body is `status`, `mode`, `mongodb`, `database.state`, `auth` only; exception types and missing variable names stay in the server log |
| `POST /api/auth/register`, `POST /api/auth/login` | public | 503 `auth_unavailable` without an account store; abuse limits are item 7 |
| `GET /api/auth/me` | auth | |
| `GET /api/mentor/teach/{concept}`, `GET /api/mentor/quiz` | public | static content, no database access |
| `POST /api/mentor/quiz` | auth when accounts are enabled, anonymous in demo | attempt stored with the token's user id; body may not carry a user id |
| `POST /api/chat`, `POST /api/chat/stream` | owner | body `{session_id?, message}`; omitting `session_id` creates a session; `thread_id`/`user_id` in the body are rejected (422) |
| `GET /api/sessions`, `GET /api/sessions/{id}` | owner | newest first; `limit` 1-50, `skip` 0-1000 |
| `GET /api/executions`, `GET /api/executions/{id}` | owner | events carry `user_id`; `limit` 1-100, `skip` 0-1000 |
| `GET /api/mentor/explain/{id}` | owner | same lookup as executions |
| `GET /api/db/collections`, `GET /api/db/sample/{name}` | auth | fixed allowlist: `full_docs`, `chunked_docs` (shared, fixed fields, no body/embedding) and `sessions`, `agent_execution_events`, `quiz_attempts` (owner-filtered); `users`, checkpoints and everything else return 403; `limit` 1-20, `skip` 0-1000 |

Conversation history uses the same ownership check as chat. Checkpoints are never exposed directly; the graph only receives thread ids that come from an owned session.

**Legacy data:** events and quiz attempts written before item 6 have no `user_id`. Every query filters on `user_id`, so they match no user and are never returned or assigned to anyone. They remain in MongoDB. No migration is provided; if one is wanted later it must be an explicit operator script with a named target user.

## Abuse limits (item 7)
Full table, counting rules and proxy notes: README "Abuse limits". Defaults: register 10/h/IP, login 10/min/IP, chat 30/min/IP and 10/min/user, other `/api` routes 120/min/IP, `/health` exempt; body cap 32768 B (4096 B for register and login). Order for a request: IP bucket, `Content-Length` check, bounded body read (all in middleware, before parsing, auth, Argon2, graph, providers, writes); then, for chat only, authentication and the per-user bucket before any session write.

| Check | Evidence |
|---|---|
| Below budget passes, first excess is 429 with `Retry-After`, recovery at the exact boundary | tests/test_limiter.py, test_protection.py (fake clock) |
| Separate register/login/chat/read buckets; health never limited | test_protection.py, test_abuse_limits.py |
| Per-user budgets independent on one IP; shared IP cap applies to all | test_abuse_limits.py |
| User key from the verified token only (header/body spoofing has no effect) | test_abuse_limits.py |
| Forwarded/X-Forwarded-For/X-Real-IP cannot rotate or redirect a budget; missing client address; IPv6 /64 | test_protection.py |
| Rejected requests do no work (Argon2, graph, session create, user create spied) | test_abuse_limits.py |
| 413 at cap+1 and for chunked bodies without Content-Length; exact cap intact; disconnect mid-body; byte cap vs character limit | test_protection.py, test_abuse_limits.py |
| Capacity behaviour, eviction only of refilled buckets, concurrent hits never exceed budget | test_limiter.py |
| 429/413 carry request id, CORS and `Retry-After` exposure; logs are throttled, traceback-free for expected errors, traceback kept for unexpected ones, no keys/bodies | test_protection.py, test_abuse_limits.py |
| Mutation checks: IP check disabled -> 22 failures; chunk counting removed -> 2; user budget removed -> 7 | run manually this session |

Not verified: behind a real reverse proxy, with several workers, under real load, against Atlas, with a provider-backed Mentor (does not exist yet).

## Security regression matrix (item 8)

`backend/tests/test_security_matrix.py` checks the registered method and path
inventory, including framework documentation routes outside OpenAPI. Its live-mode
fixture uses application-issued signed tokens, mongomock, and a fake graph.

| Policy | Routes and evidence |
|---|---|
| Public | Health, homepage, API docs, OpenAPI, registration, login, static Mentor lessons and quiz questions |
| Authenticated | Current user, quiz grading with accounts enabled, and the explorer |
| Owner-scoped detail | Chat resume, session detail, execution detail, and Mentor explanations compare foreign, missing, and legacy IDs and exercise successful owner requests |
| Owner-scoped lists | Sessions, executions, and explorer data. Execution and explorer pagination apply the owner filter before slicing |
| Middleware order | Oversized unauthenticated chat gets 413, normal unauthenticated chat gets 401, foreign session gets 404, exhausted account gets 429 before lookup, and an exhausted IP gets 429 before body validation |

The existing ownership and abuse suites cover demo grading, forbidden collections
and fields, identity spoofing, and independent account budgets on a shared IP.
These tests do not exercise Atlas, a reverse proxy, or multiple workers.

## Retrieval preflight and evaluation (items 9–11)

| Item | Local evidence | Pending |
|---|---|---|
| Shared Voyage adapter | Query payload and invalid vector handling exercised with a stubbed provider | Live Voyage response for the configured model |
| Atlas index and search | Mocked index states, idempotent setup, score filtering and source projection | Index creation and query on Atlas with the intended permissions |
| Retrieval evaluation | Original corpus, case file, metric calculation tested with fixed inputs | Live ingestion, query results and evaluation report |

## Citation provenance and chat events (items 12–13)

| Feature | Verification |
|---|---|
| Current-turn citation provenance and explicit evidence outcomes | Real LangGraph wiring with a scripted model, mongomock, and an in-memory checkpointer |
| Authenticated POST chat SSE | ASGI tests with signed tokens, scoped sessions, shared chat budgets, safe progress fields, and terminal results/errors |
| Atlas, Voyage, OpenAI, and deployed streaming | Pending live verification |

## Conversation history and long-term memory (item 14)

| Route | Policy |
|---|---|
| `GET /api/sessions/{session_id}/history` | Owner only. Returns bounded finalized turns from persisted traces |
| `GET /api/memory`, `POST /api/memory` | Authenticated. Lists or saves notes for the token user |
| `DELETE /api/memory/{memory_id}` | Owner only. Foreign and missing notes both return 404 |

Both chat entry points support explicit per-turn memory opt-in. Local tests
exercise signed tokens, isolation, deletion and graph prompt construction.

## Independent Mentor and observability (items 16–18)

| Feature | Local evidence |
|---|---|
| Deterministic Mentor graph with separate sessions, runs, and events | ASGI tests cover two accounts, owner-only trace reads, ordered walkthrough, and unchanged primary records |
| Lessons, quiz, challenges, and learning progress | Authenticated ASGI tests cover correct and incorrect answers and separate account progress |
| Bounded tool trace output and owner-scoped analytics | Scripted graph and mocked MongoDB tests cover redaction before truncation, time windows, and missing provider usage |

The Mentor workflow uses no provider. Real MongoDB aggregation, Atlas, and
deployed behavior remain unverified.

## React foundation and Agent Playground (items 19–20)

The React app is in `frontend/playground`. It uses the existing health,
account, session history, and streaming chat APIs. It supports account
registration and sign-in, owned session selection, cancellation of stream
delivery, citation inspection, and optional saved notes. Legacy HTML
remains usable through the backend. Dedicated replay and operations
screens were added in Session 13.

## React workspace operations (items 21–23)

| View | API and behavior |
|---|---|
| Execution Replay | Lists owned completed runs and plays saved trace events in order. Playground links open a selected run. Sequence gaps or incomplete terminal events are surfaced. |
| Memory Studio | Lists, saves and deletes owned personalization notes. Deletion requires an explicit second action. |
| MongoDB Explorer | Lists API-allowed collections and paginated record samples, distinguishing owned data from shared catalog data. |
| Analytics | Shows recorded execution, latency, tool and usage aggregates across selectable time windows. Missing provider usage remains unavailable. |

## React learning and project resources (items 24–25)

The Learning Center exposes all five Mentor activities, session activity,
and persisted progress. Execution Replay links to Mentor with the owned
run ID prefilled. Public Project Resources links to the existing README,
architecture, curriculum and Credly credential and accepts local JSON
from the retrieval evaluator. Report import validates the expected shape
and shows the declared run mode. No live results are bundled or verified
by the viewer.

## Benchmark runs, containers and CI (items 26–27)

| Feature | Verification |
|---|---|
| Vector and agent reports | Evaluator tests cover scoring, failed cases, exclusive file creation, and safe failure codes. Frontend tests cover report import. Live scores are pending. |
| Container configuration | Backend and React gateway have separate non-root images and health checks. CI is configured to build and start the demo and smoke-test the gateway. |
| GitHub Actions | Backend tests, frontend tests and build, and container smoke jobs are configured. The Session 15 hosted workflow passed. See [release evidence](RELEASE_EVIDENCE.md). |
