# Session handoff

Session 7 covers roadmap item 8. Base `cdc6fa4` is the published Session 6
abuse-protection commit. The route-policy matrix exercises the actual app
with signed tokens, mongomock, and a fake graph. No production code changed.

## Retrieval preflight

- `scripts/ingest_documents.py` takes a directory of Markdown/text files.
  It stores full documents and chunks in `full_docs` and `chunked_docs`.
  Existing ingestion validates vector length, but the query path does not.
- Both paths default to `voyage-3-lite` and 512 dimensions. The index script
  creates a cosine vector index on `chunked_docs.embedding` using the
  configured index name, but does not reconcile an existing index or wait.
- Full-document lookup currently uses an exact title. Ingestion skips an
  unchanged title/hash when its chunk count matches, and replaces chunks
  and the full document when content changes. A corpus is not bundled.
- Live verification needs an isolated Atlas database, a database user that
  can write the sample corpus, an index with the configured name and
  dimensions (or permission to manage it), and `VOYAGE_API_KEY` for
  embedding. The authenticated chat demo additionally needs
  `OPENAI_API_KEY` and `JWT_SECRET`. Do not share secret values in chat.

Next is item 9. Start in `backend/app/tools.py` and
`scripts/ingest_documents.py`. Share the Voyage embedding path and reject
bad query dimensions before constructing a MongoDB search.

## Verification

Baseline: 238 tests passed. Session 7: 262 passed, Ruff and Mypy clean
(23 app files), and diff checks clean. Removing the session owner filter in
an isolated copy caused three targeted tests to fail. The committed source
retains the filter. Live Atlas and providers were not exercised.

## Session 8 checkpoint — item 9

Ingestion and query embeddings now share a Voyage adapter and validate
vector count, dimensions, and finite coordinates. Voyage timeout and
retry settings now also apply to the ingestion script. The query regression
verifies that an invalid vector does not reach MongoDB. Next: item 10,
index readiness, idempotent setup, and retrieval diagnostics.

Item 9 checks: 263 passed, Ruff and Mypy clean (24 app files).
The provider was stubbed. Voyage and Atlas credentials are unavailable here.

## Session 8 checkpoint — item 10

The agent vector query checks named-index readiness and compatibility, then
applies the configured minimum score. The index CLI creates a missing
index, waits with a deadline, and leaves incompatible indexes untouched.
The application database role now needs search-index inspection permission
in addition to query permission. Tests use mocked Atlas responses.

Item 10 checks: 270 passed, Ruff and Mypy clean (25 app files).
Next: item 11, a small corpus and reproducible retrieval evaluation.

## Session 8 checkpoint — item 11

A small original corpus and versioned query set are in
`benchmarks/retrieval/`. The evaluation CLI calls the same vector query as
the agent, reports source-level Recall@k and reciprocal rank on answerable
queries, and shows whether the out-of-corpus query got any results. No
measured Atlas scores are committed.

Next: run the README live retrieval steps against an isolated Atlas
database with Voyage enabled. Then continue with item 12, structured
citations, explicit insufficient-evidence behavior, and tool failures in the
primary agent.

Session 8 checks: 271 tests passed, Ruff and Mypy clean (25 app files),
and diff checks clean. The evaluation CLI shows an explicit credentials
error with no local Atlas or Voyage configuration. Retrieval and metric
tests used mocks or deterministic fixtures. No live result was observed.

## Session 9 — item 12

The agent returns citation metadata tied to current-turn retrieval.
Invented and prior-turn citation IDs are rejected. The result distinguishes
`answered`, `insufficient_evidence`, and `retrieval_failed`. Citation ID
validation checks provenance and does not assess whether the cited text
supports every claim. Next is item 13, authenticated execution streaming.

## Session 9 — item 13

Published Sessions 7–8 were confirmed at `fdf2882`. Chat SSE shares the
JSON route's owner checks, account and IP limits. It emits session, trace,
and terminal result or failure frames. Trace frames contain metadata only.
The final answer arrives in the result. A dropped connection can leave a
graph run completing in the background. Live provider and deployment checks
remain pending.

Next: item 14. Inspect the MongoDB checkpointer and the existing
`sessions.get_owned` path before implementing owned conversation history
and the separate long-term memory feature. Then item 15 tests restart
survival against persistent MongoDB.

Local checks: 277 tests passed, Ruff and Mypy clean (26 app files), and
diff checks clean. The scripted graph and ASGI tests do not establish
real-provider grounding or deployment behavior.

## Session 10 — item 14

Session 9 was published at `394e468`. Session 10 adds owner-scoped,
paginated conversation history from finalized traces and user-managed
memory notes. Chat uses up to five notes only with explicit per-turn opt-in.
Deleting a note excludes it from subsequent lookups. Raw graph checkpoints
remain private. Next: the optional persistent MongoDB restart test.

Item 14 local checks: 283 tests passed, Ruff and Mypy clean (27 app
files), and diff checks clean. API tests used mongomock and a fake graph.

## Session 10 — item 15

The opt-in test `test_checkpoint_survives_fresh_graph_and_mongo_client`
uses MongoDBSaver and two successive clients/graph instances. Set
`TEST_MONGODB_URI` for an isolated deployment that allows creating and
dropping its generated database. The scripted model checks that the prior
user message reaches the rebuilt graph. This tests checkpoint restore
across graph/client recreation rather than a full uvicorn process restart.

Next: item 16, the independent Mentor workflow. Start by inspecting
`backend/app/mentor.py`, `routes_api.py`, and the existing scoped execution
lookup. Preserve the static lessons and quiz paths while adding the Mentor
graph and its separate owned state.

Final local checks: 283 passed, 1 skipped, Ruff and Mypy clean. The skipped
test needs `TEST_MONGODB_URI`. No real MongoDB restart was verified here.

## Session 11 — item 16

Published Session 10 ends at `bad8b16`. Mentor now has a separate,
deterministic LangGraph and owned sessions, results, and event storage.
Teach, watch, and step work without an LLM provider. Trace modes read
a bounded, allowlisted view of owned primary executions.

## Session 11 — item 17

The Mentor graph now also grades quizzes and checks project challenges.
Lessons link to relevant code and include exercises. The authenticated
progress endpoint derives lesson views, best quiz scores, and completed
challenges from the caller's persisted Mentor runs. Older standalone quiz
attempts remain in their original collection.

## Session 11 — item 18

Primary tool events retain redacted result text up to 2,000 characters and
a truncation flag. The owner-scoped analytics API aggregates actual stored
events over a 1–30-day window. Missing provider usage remains null.
Verification used mongomock and scripted graph responses.

Next: Session 12, items 19–20. Inspect `frontend/index.html` and the
existing API contracts before building the React foundation, auth, and
streaming Playground. Keep JSON chat and the existing frontend usable
until the React flow is verified.

Final local checks: 291 passed, 1 skipped, Ruff and Mypy clean (29 app
files), and diff checks clean. The skipped real MongoDB checkpoint test
requires `TEST_MONGODB_URI`.

## Session 12 — item 19

React and TypeScript foundation lives in `frontend/playground`. It uses the
existing account API, keeps its bearer token in memory, and displays
backend readiness. Vite proxies API and health calls to port 8000 in
development. The existing FastAPI-served frontend remains available.

## Session 12 — item 20

The React Playground now uses the authenticated streaming chat contract.
It resumes owned sessions, shows finalized history and current execution
progress, and displays citation metadata. It keeps the API token in
memory and clears the workspace after a 401 or token expiry. The original
FastAPI-served page remains in place. Start the React app with
`cd frontend/playground && npm ci && npm run dev`.

Next: Session 13, the execution replay, Memory Studio, MongoDB Explorer,
and analytics views. Reuse `frontend/playground/src/api.ts` and the
existing route policies.

Checks: four frontend tests passed, TypeScript/Vite production build
passed, and npm audit reported zero vulnerabilities. Backend suite:
291 passed, one real-MongoDB test skipped. A Vite-to-FastAPI HTTP smoke
test exercised registration, login, SSE parsing, and owned history with
mongomock and a scripted graph. Chromium could not launch in this
environment, so browser interaction and visual checks remain pending.

## Session 13 — items 21–23

Built on published Session 12 at `9d7be7f`. React now has dedicated views
for owned execution replay, notes, collection samples, and stored metrics.
Workspace navigation preserves the mounted Playground while signed in.
There are no backend API changes.

Next: Session 14, Mentor and Learning Center plus the benchmark,
documentation and certification views. Start from the existing Mentor
run, history, challenge and progress APIs. Keep any benchmark display
explicit about which results were actually measured.

Checks: four frontend tests passed, TypeScript/Vite build passed, and
291 backend tests passed with one real-MongoDB test skipped. The built
React app passed a simulated DOM smoke test against local FastAPI using
mongomock and a scripted graph. It exercised replay controls, note
deletion, collection samples, and analytics. Real-browser visual checks
and live MongoDB verification remain pending.

## Session 14 — items 24–25

Built on published Session 13 at `a854eb9`. The React Learning Center
covers teach, watch, step, quiz, challenge, persisted progress, and Mentor
session history. Project Resources is public and links to documentation
and the official credential. It imports evaluator JSON client-side and
ships no benchmark scores.

Six frontend tests and the production build passed. The built React app
passed a simulated DOM smoke test against local FastAPI with mongomock
and a scripted primary graph. It covered report import, the Replay to
Mentor link, all five activities, and progress. Real browser visual checks
and live-provider verification remain pending.

Next: Session 15, items 26–27. Build the reproducible benchmark runner and
stored run format, then harden Docker and wire frontend checks into CI.
Start with `scripts/evaluate_retrieval.py`, `benchmarks/retrieval`,
`deployment/`, and `.github/workflows/ci.yml`.

## Session 15 — item 26

Built on published Session 14 at `286ee58`. The evaluator supports vector
and agent strategies and saves versioned per-run JSON. Metadata records the
dataset hash, Git revision, timestamp and settings. Failure codes are
recorded without raw provider details. The report viewer imports both
strategies and distinguishes failure from no evidence. Live evaluation
still needs an isolated Atlas corpus, Voyage, and OpenAI for agent mode.

## Session 15 — item 27

Compose builds a non-root FastAPI service and a separate React/Nginx
gateway. The gateway preserves streaming and both service ports bind to
loopback. The root environment file is optional for demo and excluded
from the Docker build context. GitHub Actions now has frontend and
container smoke jobs alongside backend checks.

Next: Session 16, item 28. Reproduce the demo from a clean checkout,
inspect actual GitHub Actions results, capture working-screen evidence,
and finalize the README. Keep any live Atlas, benchmark, or deployment
claim pending until it has actually been verified.

Final checks: 292 backend tests passed and one real-MongoDB test skipped;
Ruff and Mypy passed. Seven frontend tests and the production build
passed. Docker Compose config validation and actionlint passed. No Docker
daemon was available here, so container build and startup remain pending.
The evaluator's no-credentials guard was exercised; no live benchmark
scores were generated.

## Session 16 — item 28

The release pass updates the README, separates operations and demo
guidance, and records evidence with genuine Chromium captures. The
credential-free Resources view ran against FastAPI demo mode. The
authenticated Playground and Mentor captures use a clearly labeled
scripted primary run and mongomock. A browser check exposed a duplicate
Replay action after history loaded; the final UI shows a single action.

Clean checkout checks passed: 292 backend tests (one real-MongoDB test
skipped), Ruff, Mypy, seven frontend tests, and the production build.
Hosted backend, frontend, and container demo checks passed at published
Session 15 tip `55d00a3` (GitHub Actions run `42649184362`).
Live Atlas, Voyage, OpenAI, benchmark scores, and real checkpoint
restoration remain unverified.

This is the final planned implementation session. The next action after
publication is optional live verification using `docs/DEMO.md`.

## Backend hardening follow-up

The backend adds model-selected direct responses, per-turn tool budgets,
bounded evidence and prompt history, and a process-local session guard.
See [backend hardening](docs/BACKEND_HARDENING.md) for the audit, local
verification, and remaining live deployment gates.
