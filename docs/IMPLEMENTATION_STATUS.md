# Implementation status

Statuses: COMPLETE AND VERIFIED, IMPLEMENTED BUT NOT VERIFIED, PARTIALLY IMPLEMENTED, NOT IMPLEMENTED.
Mocked tests (mongomock, scripted model, in-memory checkpointer) never count as live verification.
Last updated: session 6, after roadmap item 7. Base: 858d204 (origin/main, item 6 confirmed). Tests: 238 pass (all mocked), ruff and mypy clean.
Legend: VERIFIED LOCALLY (mocked/demo/mongomock), VERIFIED LIVE (real providers), IMPLEMENTED, VERIFICATION PENDING, PARTIAL, PLANNED. Older rows below use the earlier four-status wording; IMPLEMENTED BUT NOT VERIFIED means IMPLEMENTED, VERIFICATION PENDING.

## Phase A: backend
| Requirement | Status | Evidence / gap |
|---|---|---|
| Env configuration, startup validation | IMPLEMENTED BUT NOT VERIFIED | `config.py`, `tests/test_config.py` (mocked env). Modes auto/demo/live, ranges, URI scheme, embedding dims for known models; errors never contain values. Not exercised by a real deployment |
| Pinned dependencies | PARTIALLY IMPLEMENTED | direct deps pinned in `pyproject.toml`; clean venv install + 27 tests pass. No lock file for transitive deps; langchain-openai/voyageai imported but never called live |
| MongoDB connection lifecycle | IMPLEMENTED BUT NOT VERIFIED | `mongo.py`, FastAPI lifespan; one client, timeouts/pool options checked on a real (unconnected) PyMongo client, closed on shutdown, injectable (`tests/test_database.py`). Never connected to Atlas |
| Atlas connectivity / health check | IMPLEMENTED BUT NOT VERIFIED | `health.py`: demo / not_configured / unreachable / connected, 503 when live and not connected; tested with fake clients only |
| Structured logging | IMPLEMENTED BUT NOT VERIFIED | `logging_config.py`: JSON lines, ids, configurable redaction (tests/test_logging.py). Smoke-run under uvicorn in demo mode only |
| Request IDs | IMPLEMENTED BUT NOT VERIFIED | `middleware.py`: validated/generated, on responses, logs and execution events; concurrency tested with 30 parallel requests (mocked app) |
| Input validation | PARTIALLY IMPLEMENTED | thread_id/message/limit validated (tests/test_api.py); no body size cap at the server |
| Authentication (register, login, current user) | VERIFIED LOCALLY (mongomock, 52 tests in test_auth.py/test_config.py) | `auth.py`, `routes_auth.py`. Argon2id, HS256 tokens with required claims, uniform login errors, unique email index, concurrent-registration test. Never run against Atlas; unique-index race enforced by mongomock in tests |
| User/session ownership | VERIFIED LOCALLY (mongomock, 22 tests in test_ownership.py; mutation-checked: removing the owner filters fails 6 of them) | `sessions.py`, `routes_api.py`. Server-generated session ids, owner on every query, 404 for foreign and missing, legacy unowned records hidden. Not run against Atlas; exhaustive cross-user matrix is item 8 |
| Rate limiting, request size limits | VERIFIED LOCALLY (fake clock; real uvicorn smoke in demo mode) | `limiter.py`, `protection.py`, `routes_api.chat_budget`; 61 tests in test_limiter (15), test_protection (24), test_abuse_limits (22), plus 3 in test_config. Process-local; not tested behind a proxy, multi-worker, or live |
| LLM timeout / bounded retries | IMPLEMENTED BUT NOT VERIFIED | configurable for ChatOpenAI and the Voyage query call; never called live |
| Exception handling | IMPLEMENTED BUT NOT VERIFIED | `errors.py`: uniform error body, Mongo/LLM/embedding/timeout/step-limit classification, no values or traces to clients (tests/test_errors.py). Provider exceptions are constructed in tests, not produced by real providers |

## Phase B: vector search
| Requirement | Status | Evidence / gap |
|---|---|---|
| `$vectorSearch` aggregation | IMPLEMENTED BUT NOT VERIFIED | `tools.py`; never run |
| Vector index creation | IMPLEMENTED BUT NOT VERIFIED | `scripts/create_vector_index.py`; not idempotent, does not wait for readiness |
| Voyage embeddings, dimension validation | PARTIALLY IMPLEMENTED | dims checked at ingest (fake embedder); query call now passes a list (regression-tested with a fake client); query-side dimension unchecked; never called live |
| Configurable provider | NOT IMPLEMENTED | Voyage hardcoded |
| Similarity threshold, index-not-ready handling, diagnostics | NOT IMPLEMENTED | db_operation event records scores only |
| Resumable ingestion | PARTIALLY IMPLEMENTED | embed-then-write, hash + chunk_count (mongomock tests); no real run |
| Retrieval evaluation dataset | NOT IMPLEMENTED | |

## Phase C: primary agent
| Requirement | Status | Evidence / gap |
|---|---|---|
| Two course tools | IMPLEMENTED BUT NOT VERIFIED | executed in mocked loop only |
| LangGraph agent/tools loop, routing, recursion limit | PARTIALLY IMPLEMENTED | verified with scripted model (tests/test_graph.py); real LLM tool selection untested |
| Unknown-tool and tool-failure handling | PARTIALLY IMPLEMENTED | recorded as error event with an error_category and logged (mocked) |
| Citations, insufficient-evidence answers | PARTIALLY IMPLEMENTED | prompt-only; no structured citations, no check |
| Streaming | NOT IMPLEMENTED | |

## Phase D: memory
| Requirement | Status | Evidence / gap |
|---|---|---|
| MongoDB checkpointer | IMPLEMENTED BUT NOT VERIFIED | `MongoDBSaver`; tests swap in MemorySaver; restart survival untested |
| Session isolation | NOT IMPLEMENTED | only event filtering by thread_id in tests |
| Long-term user memory, inspection, deletion, summarization | NOT IMPLEMENTED | |

## Phase E: mentor
| Requirement | Status | Evidence / gap |
|---|---|---|
| Independent LangGraph mentor with LLM, own routes/sessions/history/tracing | NOT IMPLEMENTED | `mentor.py` is static text plus rules |
| Rule-based trace explanation, 3-question quiz | PARTIALLY IMPLEMENTED | unit-tested; keep as fallback content, not described as an agent |
| Progress persistence | PARTIALLY IMPLEMENTED | quiz attempts inserted, unauthenticated user_id |

## Phase F: frontend
Only `frontend/index.html` (one static page, escaped output). React/Vite/Tailwind app and all 12 pages: NOT IMPLEMENTED. Note: there is no frontend build step to pass or fail.

## Phase G: observability
| Requirement | Status | Evidence / gap |
|---|---|---|
| Event persistence with redaction, completeness flag | PARTIALLY IMPLEMENTED | `tracing.py`, mocked tests; no user id on events, tool results truncated to a 300-char preview |
| Timeline UI, analytics, filters, token usage views | NOT IMPLEMENTED | |

## Phase H: evaluation
No dataset, scripts or results. NOT IMPLEMENTED. No benchmark number exists.

## Phase I: docs and deployment
| Requirement | Status | Evidence / gap |
|---|---|---|
| README, audit notes | PARTIALLY IMPLEMENTED | no architecture/API/DB docs |
| Dockerfile / Compose | PARTIALLY IMPLEMENTED | builds untested here; root user, no healthcheck |
| CI | PARTIALLY IMPLEMENTED | `.github/workflows/ci.yml` runs ruff, mypy, pytest; never executed on GitHub |
| Screenshots | NOT IMPLEMENTED | none until the app runs |
| Credly link, badge vs project achievements | COMPLETE AND VERIFIED | README; certificate image checked against the claims |

## Route policy (after item 6)
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
