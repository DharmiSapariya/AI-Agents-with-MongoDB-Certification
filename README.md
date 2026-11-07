<!-- ============ TOP OF README (hero badge) ============ -->
<p align="center">
  <a href="https://www.credly.com/badges/9b5d068b-0566-479f-812b-93b06d01041b">
    <img src="assets/certification/mongodb-ai-agents-badge.png" alt="MongoDB Skill Badge: AI Agents with MongoDB" width="140" />
  </a>
</p>

<p align="center">
  <a href="https://www.credly.com/badges/9b5d068b-0566-479f-812b-93b06d01041b">
    <img src="https://img.shields.io/badge/MongoDB%20Skill-AI%20Agents%20with%20MongoDB-00ED64?style=for-the-badge&logo=mongodb&logoColor=white&labelColor=023430" alt="MongoDB Skill Badge" />
  </a>
</p>



# MongoDB AI Agent Platform

A MongoDB-backed multi-tool AI agent (LangGraph + Atlas Vector Search + MongoDB checkpointing), with a second **Mentor** component that explains Agent One's *recorded* execution traces. Based on the MongoDB University course *Building AI Agents with MongoDB*.

<!-- ============ CERTIFICATION SECTION (place after the intro / problem statement) ============ -->
## 🏅 Certification

This project builds on the official **MongoDB Skill badge: AI Agents with MongoDB**, earned by completing the *Building AI Agents with MongoDB* course on MongoDB University.

| | |
|---|---|
| **Credential** | MongoDB Skill: AI Agents with MongoDB |
| **Course** | Building AI Agents with MongoDB |
| **Issued by** | MongoDB, Inc. |
| **Completed on** | November 4, 2026 |
| **Verify** | [Credly badge](https://www.credly.com/badges/9b5d068b-0566-479f-812b-93b06d01041b) |

<p align="center">
  <a href="https://www.credly.com/badges/9b5d068b-0566-479f-812b-93b06d01041b">
    <img src="assets/certification/mongodb-ai-agents-badge.png" alt="MongoDB Skill Badge" width="180" />
  </a>
  &nbsp;&nbsp;&nbsp;
  <a href="assets/certification/mongodb-ai-agents-certificate.pdf">
    <img src="assets/certification/mongodb-ai-agents-certificate.png" alt="MongoDB Proof of Completion certificate" width="480" />
  </a>
</p>

<p align="center">
  <sub>Click the badge to verify on Credly · Click the certificate to open the PDF</sub>
</p>

> **Note:** The badge and Proof of Completion above are the *official* credentials issued by MongoDB.
> Any achievements or completion marks inside this application's Certification page are
> project-generated learning milestones and are not MongoDB credentials.

## Status (honest)

| Area | Status |
|---|---|
| Agent One: 2 course tools, LangGraph loop, conditional routing, MongoDB checkpointer | IMPLEMENTED BUT NOT VERIFIED (needs Atlas + OpenAI + Voyage keys) |
| Event tracing to `agent_execution_events` with redaction and "fully_recorded" flag | IMPLEMENTED; redaction/tracer logic unit-tested, live DB path not verified |
| Agent Two (Mentor): static concept text, rule-based trace explanation, 3-question quiz | IMPLEMENTED; unit-tested. It is not an LLM agent: no model, graph or per-user history |
| Ingestion (embed-then-write, batched, resumable by hash + chunk count) | Logic tested with mongomock and a fake embedder; real Voyage/Atlas run NOT VERIFIED |
| Vector index and regular index scripts | IMPLEMENTED BUT NOT VERIFIED against Atlas |
| Frontend | PARTIAL: one static page (chat + mentor), trace data HTML-escaped |
| Accounts and access tokens (`/api/auth/register`, `/login`, `/me`) | VERIFIED LOCALLY against mongomock (151 tests); not run against Atlas |
| Per-user ownership of sessions/traces, rate limiting | NOT IMPLEMENTED. Only `/api/auth/me` requires a token: `/api/chat`, `/api/executions*`, `/api/db/*` and mentor routes are still open, so anyone who can reach the server can call the LLM, read traces and use any thread_id |
| Long-term memory, SSE live updates, observability dashboard, DB explorer UI, benchmarks, step-through playback, learning-center modules, React frontend | NOT IMPLEMENTED |
| Direct dependencies pinned; CI runs ruff, mypy and pytest | Pinned versions install cleanly and pass locally; CI has not been observed running on GitHub; no lockfile for transitive packages |
| Startup settings validation, JSON logging, request IDs, MongoDB lifecycle, health states, standard error responses | IMPLEMENTED; covered by mocked tests (fake clients, mongomock), not run against Atlas |

No screenshots, benchmark numbers or deployment are claimed. The course dataset is not bundled: ingest your own docs.

## Run
```bash
cp .env.example .env        # fill in keys
make install && make test   # no keys needed; tests use mongomock and a scripted model, not Atlas
python scripts/create_indexes.py
python scripts/ingest_documents.py ./my_docs
python scripts/create_vector_index.py
make run                    # http://localhost:8000
```
Without keys the app runs in **demo mode**: mentor teaching and quiz work; agent, traces and DB views return 503 with code `demo_mode`.

## Configuration
Settings come from the environment or `backend/.env` and are validated at startup. A bad value stops the app with a message that names the variable, never its value.

| Variable | Default | Notes |
|---|---|---|
| `APP_MODE` | `auto` | `auto`: live when all three credentials are set, otherwise demo. `demo`: never contact services. `live`: refuse to start unless configured |
| `MONGODB_URI`, `OPENAI_API_KEY`, `VOYAGE_API_KEY` | empty | all three are required for live mode; `MONGODB_URI` must start with `mongodb://` or `mongodb+srv://` |
| `DB_NAME`, `CHECKPOINT_DB` | `ai_agents`, `checkpointing_db` | letters, digits, `_`, `-` |
| `LLM_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMS` | `gpt-4o`, `voyage-3-lite`, `512` | dimensions are checked against known Voyage models (`voyage-3-lite` 512, `voyage-3` 1024) |
| `MAX_GRAPH_STEPS` | `12` | 2-50, agent recursion limit |
| `MONGO_TIMEOUT_MS`, `MONGO_SOCKET_TIMEOUT_MS`, `MONGO_MAX_POOL_SIZE` | `5000`, `30000`, `20` | server selection and connect timeout, socket timeout, pool size |
| `LLM_TIMEOUT_S`, `LLM_MAX_RETRIES`, `EMBEDDING_TIMEOUT_S`, `EMBEDDING_MAX_RETRIES` | `30`, `2`, `15`, `2` | per-call timeout and retry limit |
| `JWT_SECRET` | empty | HS256 signing key, at least 32 characters. Required when `APP_MODE=live`; without it the auth routes return 503 `auth_unavailable` |
| `JWT_ISSUER`, `JWT_AUDIENCE`, `ACCESS_TOKEN_TTL_MINUTES` | `mongodb-ai-agent-platform`, `mongodb-ai-agent-platform-api`, `30` | token claims checked on every request; lifetime 1-1440 minutes |
| `AUTH_MAX_CONCURRENT_HASHES` | `4` | caps simultaneous Argon2 hashes (each uses 64 MiB) until request rate limits exist |
| `LOG_LEVEL`, `LOG_REDACT_PATTERNS` | `INFO`, `[]` | extra regexes (JSON list) masked in logs, on top of built-in secret patterns |

## Authentication
Accounts live in the `users` collection (`_id` random hex, normalized `email` with a unique index, Argon2id `password_hash`, `created_at`).

```bash
curl -X POST localhost:8000/api/auth/register -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"a passphrase of 12+ chars"}'
curl -X POST localhost:8000/api/auth/login -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"a passphrase of 12+ chars"}'   # -> {"access_token": ..., "expires_in": 1800}
curl localhost:8000/api/auth/me -H "Authorization: Bearer $TOKEN"
```
- **Email rule:** ASCII only, trimmed, lowercased; the same function runs on register and login.
- **Passwords:** 12-128 characters, hashed as given (no truncation or normalization). Argon2id, 64 MiB, 3 passes.
- **Login errors:** unknown email, bad format and wrong password all return the same 401 `invalid_credentials` and each costs one Argon2 verification.
- **Tokens:** HS256, 30 minutes by default. `iss`, `aud`, `sub`, `iat`, `nbf`, `exp` and `jti` are required; any failure returns 401 `invalid_token` with `WWW-Authenticate: Bearer error="invalid_token"`. A missing header returns 401 `not_authenticated`. There are no refresh tokens, password reset, email verification or OAuth.
- **Registering an existing email returns 409 `email_taken`**, which reveals that the account exists. Hiding that needs email verification, which is out of scope.
- In demo mode, or without `MONGODB_URI` / `JWT_SECRET`, all three routes return 503 `auth_unavailable`.

## Operations
- **Logs** are one JSON object per line on stdout: `ts`, `level`, `logger`, `event`, plus `request_id` and `execution_id` when known. Each request produces a `request_completed` line (method, route, status, duration). Prompts, answers and retrieved text are not logged.
- **Request IDs**: send `X-Request-ID` (8-64 chars of `A-Za-z0-9._-`) or one is generated. It is returned on every response, appears in logs and is stored on execution events as `request_id`.
- **Health**: `GET /health` returns `mongodb` as `demo`, `not_configured`, `unreachable` or `connected`. `connected` is reported only after a ping succeeds. Live mode with an unreachable database returns HTTP 503. The app starts even if Atlas is down, so this endpoint can report it.
- **Errors** are `{"error": {"code", "message", "request_id"}}`. Codes include `validation_error`, `demo_mode`, `database_unavailable`, `database_timeout`, `llm_provider_error`, `llm_timeout`, `embedding_provider_error`, `execution_limit_exceeded`, `timeout`, `internal_error`. Stack traces and exception messages go only to the redacted server log.

## Collections used
`chunked_docs`, `full_docs`, `agent_execution_events`, `quiz_attempts`, plus LangGraph's `checkpoints` / `checkpoint_writes` in `checkpointing_db`.

## Security notes
Secrets come from env only and are redacted from traces. Retrieved text is wrapped as untrusted data. A recursion limit caps agent loops. The DB sample endpoint is read-only on an allowlist and hides embeddings. Agent tools are read-only.

## Credits
MongoDB University: *AI Agents with MongoDB* course.
