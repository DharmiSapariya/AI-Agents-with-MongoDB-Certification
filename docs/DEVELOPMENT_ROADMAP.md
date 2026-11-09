# Development roadmap

Order follows the project brief. Each item is one commit unless noted; tests run before every commit.
Live-Atlas items stay "pending live verification" until run against a real cluster with credentials.

## Phase A: backend
1. docs: roadmap, status, decisions (done, session 1)
2. chore: pin dependencies, add ruff and mypy config, run both in CI (done, session 1)
3. feat(config): validate settings at startup; structured logging; request IDs (done, session 3)
4. feat(database): connection lifecycle (close on shutdown, pool/timeouts), health detail (done, session 3)
5. feat(auth): users, password hashing, signed tokens, `/api/auth/*` (done, session 4)
6. feat(sessions): server-generated thread ids, ownership checks on chat, executions, db routes (done, session 5/6)
7. feat(security): per-user and per-IP rate limits, request size limit (done, session 6; safe error schema done, session 3)
8. test(security): cross-user access tests for every route (done, session 7)

## Phase B: retrieval
9. feat(embeddings): provider interface, Voyage implementation, query-side dimension check (done, session 8)
10. feat(search): threshold, index-not-ready error, diagnostics; idempotent index script that waits (implemented, live verification pending)
11. feat(evaluation): retrieval dataset and script (results only from real runs) (implemented, live verification pending)

## Phase C/D: agent and memory
12. feat(agent): structured citations, insufficient-evidence rule, tool-failure handling (implemented, live verification pending)
13. feat(api): streaming endpoint (implemented, live verification pending)
14. feat(memory): checkpoint restore through ownership, history endpoint, long-term memory with approval and deletion (implemented, live verification pending)
15. test: restart-survival test (pending live)

## Phase E/G: mentor and observability
16. feat(mentor): independent graph, routes, sessions, tracing
17. feat(mentor): teach, watch, step-through, quiz, challenge; progress persistence
18. feat(observability): user ids on events, full tool results with caps, analytics endpoints

## Phase F: frontend (one commit per page group)
19. foundation and auth; 20. playground with streaming; 21. live execution; 22. memory and explorer; 23. observability; 24. mentor and learning center; 25. benchmarks, documentation, certification

## Phase H/I
26. feat(evaluation): benchmark runner and stored runs; 27. Docker hardening and healthchecks; 28. docs finalisation with real screenshots

## What is blocked on the user
Atlas connection string with a vector index, OpenAI key, Voyage key, and a GitHub remote. Independent work continues without them.
