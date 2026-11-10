# Backend hardening and verification

This pass extends the existing authenticated MongoDB learning agent. The
FastAPI chat endpoints run one LangGraph agent, record execution events,
and return either a cited answer, a clearly identified direct answer, or
an explicit evidence failure. The frontend is outside this pass.

## Audit and changes

- Citation validation previously discarded every answer without a citation.
  The model can now explicitly choose a direct response for general knowledge.
  Direct responses require zero tool attempts and return an empty citation list.
  When tools are used, the graph resolves cited IDs from this execution only.
  This verifies citation provenance. Semantic entailment remains unevaluated.
- A graph step can execute multiple tool calls. Each requested call now
  consumes a slot, up to eight executions by default. Calls beyond the
  budget receive a paired tool result so the model can finish using evidence
  it already collected. LangGraph's separate recursion bound still applies.
- The model prompt retains recent complete turns, omits abandoned earlier
  turns, and keeps all messages in the current turn. MongoDB checkpoints
  still store conversation state, so prompt pruning has no retention effect.
- A process-local session guard prevents overlapping graph execution for a
  session. JSON chat returns 409 with `session_busy`. Once SSE has started,
  failures use its terminal `failed` event. The guard releases even if a
  provider raises. Multiple workers require shared coordination.
- Retrieval validates bounded arguments, overfetches up to four times the
  requested top-k, removes identical whitespace-normalized passages, and
  caps evidence size. Retrieved evidence includes source and truncation
  metadata. The optional exact-source filter applies after candidate
  generation and can reduce recall. The current index remains compatible.
- The retrieval evaluator reports unique relevant source precision at k
  and duplicate-source rate alongside recall and reciprocal rank. These are
  metric implementations with deterministic fixtures. No Atlas score was measured.

## Execution and data flow

```text
Authenticated chat -> owner-scoped session -> LangGraph model
  -> selected typed tool(s) -> MongoDB or Voyage + Atlas Vector Search
  -> model follow-up or final answer -> citation resolution -> JSON/SSE
```

The model requests tools dynamically within the available tool registry.
A scripted test requests two different full pages across separate model
rounds and cites evidence from both. A semantic tool test separately checks
source filtering inputs and passage deduplication. A separate test chooses
the direct path with no retrieval. These exercise the real graph with a
scripted model. The existing Mentor replays traces and remains deterministic.

Existing MongoDB integration includes full documents, vector chunks,
users, sessions, execution events, saved memory notes, and a separate
LangGraph checkpoint database. Recent conversation comes from checkpoints.
Saved notes remain a separately controlled input and are escaped when
inserted into the model prompt. Live checkpoint restoration after replacing
the MongoDB client remains an opt-in verification step.

## Configuration

| Variable | Default | Maximum | Scope |
| --- | ---: | ---: | --- |
| `MAX_TOOL_CALLS` | 8 | 30 | Tool executions per turn |
| `MODEL_HISTORY_TURNS` | 6 | 20 | Prior complete turns in the prompt |
| `RETRIEVAL_TOP_K` | 5 | 15 | Unique passages returned to the model |
| `RETRIEVAL_CHUNK_CHARS` | 2000 | 4000 | Characters per semantic result |
| `FULL_DOCUMENT_CHARS` | 20000 | 50000 | Characters of full-page evidence |

Traces record retrieval candidate counts, returned IDs and scores, the tool
budget rejection, and the final outcome. Handled tool failures log their
category without a traceback. Existing ownership checks, request size
limits, and rate limits continue to apply.

## Verification and deployment

Run the backend checks with the dependencies installed as described in
[the README](../README.md).

```bash
cd backend
pytest -q
ruff check . ../scripts
mypy app
```

Observed locally: 301 passed, 2 skipped. Ruff, mypy, and Git's whitespace
check passed. The skips cover the real MongoDB checkpoint check and the
full Atlas and model integration check. The current patch was not deployed.

Provision the isolated Atlas corpus and vector index using
[the demo setup](DEMO.md). Configure the backend for live mode with the
required MongoDB, OpenAI, Voyage, and signing credentials. Set both the
corpus and checkpoint database names to distinct names beginning with
`agent_verify_`. Then run the integration test from `backend`.

```bash
APP_MODE=live RUN_LIVE_PLATFORM_TESTS=1 pytest -q tests/test_live_platform.py
```

For an isolated standalone checkpoint check, set `TEST_MONGODB_URI` and run
`pytest -q tests/test_graph.py -k checkpoint_survives`. For hosted operation,
see [the deployment and smoke check commands](OPERATIONS.md). A single
worker preserves the limits and session guard implemented in this version.
A real deployment still needs live test evidence, benchmark results,
production proxy checks, and shared enforcement before scaling workers.

## Provisional assessment

| Category | Score | Evidence and remaining work |
| --- | ---: | --- |
| LLM architecture | 14/20 | Scripted model drives multiple tool rounds. Verify provider decisions and grounded responses live. |
| MongoDB | 7/15 | Adapter and fixture tests cover queries. Verify Atlas, index readiness, and checkpoint restore. |
| Retrieval | 9/15 | Bounded vector and full-page paths plus tested metrics. Run corpus evaluation and measure filtered recall. |
| Memory | 6/10 | Prompt pruning and saved-note tests pass. Verify live restore and define checkpoint retention. |
| Backend API | 8/10 | Authenticated routes, structured errors, and SSE coverage. Verify deployed proxy and reconnect behavior. |
| Reliability and security | 7/10 | Owner isolation, limits, and session concurrency checks pass locally. Validate shared enforcement before scaling. |
| Testing and evaluation | 8/10 | 301 passing tests. Run live checks and record benchmark results. |
| Observability | 4/5 | Execution events, request IDs, and structured logs exist. Validate deployed monitoring. |
| Deployment and docs | 4/5 | Container and runbooks exist. Deploy and smoke test the current revision. |
| **Total** | **67/100** | **Provisional, based on local evidence.** |

Resume entry: Built a FastAPI and LangGraph learning agent with
model-selected retrieval tools, MongoDB-backed sessions and checkpoints,
citation validation, and execution tracing. Added tool budgets and
retrieval quality metrics and verified the backend with 301 local tests.
