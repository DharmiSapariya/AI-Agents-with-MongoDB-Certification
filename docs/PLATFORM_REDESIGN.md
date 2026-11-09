# Platform redesign

This pass keeps the existing FastAPI, MongoDB, LangGraph, and React contracts.
The public Overview explains the execution flow with selectable stages.
After signing in, the dashboard reads the account's seven-day analytics
and latest executions. The Playground adds a session-ID filter, example
questions, response copying, and a collapsible inspector for streamed
events and citation metadata.

| Brief area | Current behavior | Open work |
|---|---|---|
| Public experience | Overview and architecture guide, with links to sign-in and public resources | Further visual refinement |
| Dashboard | Recorded account activity and replay links from the existing API | Conversation and retrieval-specific summaries |
| Primary workspace | Streaming progress, owned history, source references and run inspector | Markdown/code rendering, and richer safe tool metadata in the inspector |
| Mentor | Independent deterministic graph using an allowlisted trace projection, plus lessons and progress | Provider-backed conversational Mentor and expanded curriculum |
| Explorer | Read-only allowlisted collection samples | Collection-wide schema and index inspection with an explicit access policy |
| Evaluation | CLI runs and local report import | Run launching and management inside the app; live provider measurements |
| Persistence | MongoDB checkpointing and opt-in real MongoDB test | Real deployment restart and live retrieval verification |

No sample numbers are inserted into the dashboard. It distinguishes an
empty account from an unavailable response. The architecture guide is
conceptual. Recorded execution events come from the chat API.

## Verification

The seven existing frontend tests and production build passed.
A Chromium walkthrough covered the architecture controls, registration,
the empty and populated dashboard, streaming, the inspector toggle,
session filtering, replay, and Mentor. The public Overview was checked
at a 390-pixel viewport for horizontal overflow. The test used the real
FastAPI routes with mongomock and a scripted primary graph.

## Workspace pass

- The authenticated shell groups the existing routes in a collapsible sidebar
  with page search. Public navigation stays available without an account.
- Execution Replay displays a progress bar, recorded event payloads, and
  page-local ID and outcome filters. It reads saved events and makes no
  inference calls.
- The Explorer exposes observed sample fields and expandable JSON values
  under the existing read-only allowlist. Search applies to the current
  sample page. Memory Studio adds page-local note search.
- Mentor adds exercises for MongoDB collections, embeddings, RAG,
  checkpointing, and separation of agent responsibilities. The Mentor
  remains a deterministic graph with saved progress.
- Project Resources accepts a second retrieval report and compares scores
  only when dataset hash, cases, mode, and retrieval settings agree. The
  viewer cannot establish corpus identity from that metadata alone.

## Live integration check

Use a dedicated Atlas test deployment and export the configuration in the
[demo walkthrough](DEMO.md#live-walkthrough). Both database names must start
with `agent_verify_` and must be different. Prepare the bundled corpus,
regular indexes, and vector index as documented. Then run:

```bash
cd backend
APP_MODE=live RUN_LIVE_PLATFORM_TESTS=1 pytest -q tests/test_live_platform.py
```

The test checks the real vector index and Voyage embedding, exact document
lookup, account flow, cited primary answer, stored trace, Mentor explanation,
and checkpoint recovery with a fresh client and graph. It writes a test
account and run records to the isolated deployment. It leaves them there
for inspection. A full FastAPI process restart remains a separate live
walkthrough check.

No provider credentials were available in this environment, so the live
test and the real MongoDB checkpoint test were skipped. The local suite
uses fixtures and does not establish live model behavior.


## Workspace evidence

Chromium exercised navigation, sign-in, real API-backed dashboard states,
streamed execution inspection, replay and Mentor, filtering, and report
comparison. The primary run was scripted and used mongomock. The overview
was also checked at a 390-pixel viewport for horizontal overflow.

- [Public overview](../assets/screenshots/workspace/overview-fixture.png)
- [Signed-in dashboard](../assets/screenshots/workspace/dashboard-fixture.png)
- [Recorded execution details](../assets/screenshots/workspace/execution-fixture.png)

Local checks passed with 293 backend tests, 2 skipped, 8 frontend tests,
Ruff, Mypy, and the production frontend build.
