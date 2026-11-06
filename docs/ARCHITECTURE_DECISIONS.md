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
