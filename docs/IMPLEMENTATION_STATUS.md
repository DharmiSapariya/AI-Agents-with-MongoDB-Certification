# Implementation status

Statuses: COMPLETE AND VERIFIED, IMPLEMENTED BUT NOT VERIFIED, PARTIALLY IMPLEMENTED, NOT IMPLEMENTED.
Mocked tests (mongomock, scripted model, in-memory checkpointer) never count as live verification.
Last updated: session 1, after roadmap item 2. Remote: none configured. Tests: 27 pass (all mocked); ruff and mypy clean locally.

## Phase A: backend
| Requirement | Status | Evidence / gap |
|---|---|---|
| Env configuration | PARTIALLY IMPLEMENTED | `config.py` (pydantic-settings); no per-environment profiles, no validation of URI shape |
| Pinned dependencies | PARTIALLY IMPLEMENTED | direct deps pinned in `pyproject.toml`; clean venv install + 27 tests pass. No lock file for transitive deps; langchain-openai/voyageai imported but never called live |
| MongoDB connection lifecycle | PARTIALLY IMPLEMENTED | `mongo.py` lru_cache client, no close on shutdown, no pool settings |
| Atlas connectivity / health check | IMPLEMENTED BUT NOT VERIFIED | `/health` pings; never run against Atlas |
| Structured logging, request IDs | NOT IMPLEMENTED | |
| Input validation | PARTIALLY IMPLEMENTED | thread_id/message/limit validated (tests/test_api.py); no body size cap at the server |
| Authentication, user/session ownership | NOT IMPLEMENTED | any caller can use any thread_id and read all traces |
| Rate limiting | NOT IMPLEMENTED | |
| LLM timeout / bounded retries | PARTIALLY IMPLEMENTED | ChatOpenAI timeout=30, max_retries=2 (unverified); Voyage call has none |
| Exception handling | PARTIALLY IMPLEMENTED | graph errors re-raised as 500; no error schema |

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
| Unknown-tool and tool-failure handling | PARTIALLY IMPLEMENTED | recorded as error event (mocked) |
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
