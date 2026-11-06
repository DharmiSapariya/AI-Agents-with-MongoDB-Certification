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
| Authentication, rate limiting, per-user session ownership | NOT IMPLEMENTED: anyone who can reach the server can call the LLM, read traces and use any thread_id |
| Long-term memory, SSE live updates, observability dashboard, DB explorer UI, benchmarks, step-through playback, learning-center modules, React frontend, CI | NOT IMPLEMENTED |
| Dependency lockfile | NOT DONE (versions unpinned, not checked against current docs) |

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
Without keys the app runs in **demo mode**: mentor teaching and quiz work; agent, traces and DB views return 503.

## Collections used
`chunked_docs`, `full_docs`, `agent_execution_events`, `quiz_attempts`, plus LangGraph's `checkpoints` / `checkpoint_writes` in `checkpointing_db`.

## Security notes
Secrets come from env only and are redacted from traces. Retrieved text is wrapped as untrusted data. A recursion limit caps agent loops. The DB sample endpoint is read-only on an allowlist and hides embeddings. Agent tools are read-only.

## Credits
MongoDB University: *AI Agents with MongoDB* course.
