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
| Explorer | Read-only allowlisted collection samples | Index and schema views with an explicit access policy |
| Evaluation | CLI runs and local report import | Comparison and run management inside the app; live provider measurements |
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
