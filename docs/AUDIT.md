# Audit notes (2026-11-05)

Method: read all source, ran the test suite, ran the app in demo mode, drove the real LangGraph
loop with a scripted model and mongomock. Not possible here: Atlas, OpenAI and Voyage calls
(no credentials), so Vector Search, the Mongo checkpointer and live LLM behaviour are unverified.

## Fixed
| Sev | File | Issue | Fix / check |
|---|---|---|---|
| High | frontend/index.html | Trace data (incl. retrieved text, user input) injected via innerHTML: stored XSS | escaped; inline script run in node against a hostile trace |
| High | scripts/ingest_documents.py | Chunks deleted before embedding, full_docs hash written first: a failed run looked complete and was skipped | app/ingest.py, tests/test_ingest.py |
| Medium | backend/app/tools.py | Document text could close `</retrieved_document>` and escape the untrusted wrapper | wrap_document, tests/test_tools.py |
| Medium | backend/app/main.py | `limit` accepted 0/negative | Query(ge=1, le=100) |
| Medium | (none) | No indexes for event/title lookups | app/indexes.py, scripts/create_indexes.py |
| Low | frontend/index.html | Every visitor shared thread `demo-1` | random per-page id |
| Docs | README.md | Mentor described as an independent agent; it is static text plus rules | reworded, status table corrected |

## Open, by severity
1. High (if deployed): no auth or rate limit. /api/chat spends LLM credits; /api/executions and /api/db/* expose traces and collection names; any thread_id can be resumed by anyone. Needs an API key or login, per-user thread ownership, rate limiting. Verify: unauthenticated request returns 401; second user cannot read first user's thread.
2. High (vs. stated goals): Atlas integration, `$vectorSearch`, MongoDBSaver checkpoint restore and real LLM tool selection have never been run. Verify: run against a real cluster, ingest sample docs, ask a question, restart the server, continue the same thread.
3. Medium: Mentor is not an agent (no LLM, graph or history). Either build it or keep the README wording.
4. Medium: vector search has no score threshold, so "insufficient evidence" depends on the model. Add a minimum score and record it in the db_operation event.
5. Medium: Voyage embedding call has no timeout/retry and builds a client per query; `_app` lazy init is not thread-safe.
6. Medium: no long-term memory, benchmarks, SSE, DB explorer UI, or React frontend (README already says so).
7. Low: executions list only shows runs whose execution_end persisted; events have no TTL; user input is stored unredacted beyond secret patterns; dependencies unpinned; Docker runs as root with no healthcheck; no lint/type checks in CI.
