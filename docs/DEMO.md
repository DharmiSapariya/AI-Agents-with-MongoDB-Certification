# Demo walkthrough

## Credential-free walkthrough

Follow the [local run instructions](../README.md#run). Check
`http://localhost:8000/health` for `mode: demo`. Open the React workspace
and select **Project Resources** to inspect the setup guide and credential.
Use the original page on port 8000 for public Mentor concepts and the quiz.
The demo's authentication and chat endpoints report that they are unavailable.

## Live walkthrough

Use an isolated Atlas database. Set `MONGODB_URI`, `DB_NAME`,
`CHECKPOINT_DB`, `VOYAGE_API_KEY`, `OPENAI_API_KEY`, and `JWT_SECRET` in
your local environment. Choose a fresh `DB_NAME` and `CHECKPOINT_DB`.
Use a database account with access to both, plus the permissions needed to
create the evaluation index. Keep credential values out of source control.

With the Python environment active, run from the repository root:

```bash
python scripts/create_indexes.py
python scripts/ingest_documents.py benchmarks/retrieval/corpus
python scripts/create_vector_index.py --wait-seconds 120
APP_MODE=live make run
```

Open React as described in the [README](../README.md#run). To demonstrate
the primary agent and Mentor:

1. Register or sign in. Send “Can I use the first field of a compound
   index by itself?” in a new conversation.
2. Open **Evidence**. Check the title, collection, document ID, and chunk
   index against the retrieved record. If the run has insufficient evidence
   or a retrieval failure, show that outcome.
3. Select **Replay run**. Step through the recorded agent, tool, and database
   events. Choose **Open in Mentor** and run **Watch a trace**.
4. Save a note in **Memory Studio**. Enable **Use my saved notes** for a chat
   turn. Delete the note, then verify it disappears from the owned list.
5. Restart FastAPI. Reopen the same session and send a follow-up. The
   [real MongoDB check](OPERATIONS.md) can separately verify that the
   prior turn reaches a rebuilt graph through the checkpointer.
6. Run both evaluation strategies from the [README](../README.md#live-retrieval-evaluation).
   Import each JSON report in **Project Resources** and compare the same
   dataset and top-k. Include failures when presenting results.

The trace and citation results depend on the configured model and corpus.
Record the observed outcome and run ID when presenting the live walkthrough.

## Interview walkthrough

- Start with the boundary between retrieval and generation. Show how a
  document ID reaches the citation response and how the server rejects a
  citation ID from an earlier turn.
- Follow one request through the shared rate limit, authenticated session,
  graph, and trace. Explain why a foreign run ID receives the same response
  as an unknown ID.
- Open the same run in Mentor. Its separate state and restricted trace
  projection make it possible to teach the execution without replaying tool
  calls or exposing raw prompts.
- Close with the evidence. Local tests cover the API and a scripted graph.
  Live evaluation, real checkpoint restoration, and deployed behavior each
  need their own checks.
