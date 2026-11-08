# Implementation status

Statuses: COMPLETE AND VERIFIED, IMPLEMENTED BUT NOT VERIFIED, PARTIALLY IMPLEMENTED, NOT IMPLEMENTED.
Mocked tests (mongomock, scripted model, in-memory checkpointer) never count as live verification.
Last updated: session 5/6 work, after roadmap item 6. Base: ef357f0 (origin/main). Tests: 174 pass (all mocked), ruff and mypy clean.
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
| Rate limiting | NOT IMPLEMENTED | |
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
| `POST /api/chat` | owner | body `{session_id?, message}`; omitting `session_id` creates a session; `thread_id`/`user_id` in the body are rejected (422) |
| `GET /api/sessions`, `GET /api/sessions/{id}` | owner | newest first; `limit` 1-50, `skip` 0-1000 |
| `GET /api/executions`, `GET /api/executions/{id}` | owner | events carry `user_id`; `limit` 1-100, `skip` 0-1000 |
| `GET /api/mentor/explain/{id}` | owner | same lookup as executions |
| `GET /api/db/collections`, `GET /api/db/sample/{name}` | auth | fixed allowlist: `full_docs`, `chunked_docs` (shared, fixed fields, no body/embedding) and `sessions`, `agent_execution_events`, `quiz_attempts` (owner-filtered); `users`, checkpoints and everything else return 403; `limit` 1-20, `skip` 0-1000 |

Not yet present, and must use `sessions.get_owned` when added: conversation history/messages endpoint (roadmap 14), streaming endpoint (13), long-term memory (14). Checkpoints are never exposed directly; the graph only receives thread ids that come from an owned session.

**Legacy data:** events and quiz attempts written before item 6 have no `user_id`. Every query filters on `user_id`, so they match no user and are never returned or assigned to anyone. They remain in MongoDB. No migration is provided; if one is wanted later it must be an explicit operator script with a named target user.
