"""The two course tools (faithful to the official lesson) plus tracing and prompt-injection framing."""
import html
import re
import time
from typing import Annotated

from langchain_core.tools import tool
from pydantic import Field

from .config import settings
from .embeddings import VoyageEmbeddingProvider
from .mongo import db
from .retrieval import vector_search
from .tracing import CURRENT, emit

Query = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]
Title = Annotated[str, Field(min_length=1, max_length=512, pattern=r"\S")]
Source = Annotated[str, Field(min_length=1, max_length=512, pattern=r"\S")]

_WRAPPER_TAG = re.compile(r"<(\s*/?\s*retrieved_document)", re.I)


def wrap_document(title: str, body: str, citation_id: str = "", *,
                  source: str | None = None, score: float | None = None, truncated: bool = False) -> str:
    """Wrap retrieved text as untrusted data; a document cannot close the wrapper early."""
    safe_body = _WRAPPER_TAG.sub(r"&lt;\1", body)
    citation = f' citation="{citation_id}"' if citation_id else ""
    location = f' source="{html.escape(source, quote=True)}"' if source else ""
    similarity = f' score="{score:.4f}"' if score is not None else ""
    limited = ' truncated="true"' if truncated else ""
    return (f'<retrieved_document{citation} title="{html.escape(title, quote=True)}"'
            f'{location}{similarity}{limited}>\n{safe_body}\n</retrieved_document>')


def cite_document(doc: dict, collection: str, max_chars: int) -> str:
    body = doc.get("body", "")
    truncated = len(body) > max_chars
    tracer = CURRENT.get()
    citation_id = ""
    if tracer is not None:
        citation_id = f"S-{tracer.execution_id}-{len(tracer.sources) + 1}"
        tracer.sources[citation_id] = {
            "id": citation_id, "document_id": str(doc["_id"]), "collection": collection,
            "title": doc.get("title", "unknown"), "source": doc.get("source"),
            "chunk_index": doc.get("chunk_index"), "score": doc.get("score"), "truncated": truncated,
        }
    return wrap_document(doc.get("title", "unknown"), body[:max_chars], citation_id,
                         source=doc.get("source"), score=doc.get("score"), truncated=truncated)


def generate_embedding(text: str) -> list[float]:
    return VoyageEmbeddingProvider(settings).embed([text], "query")[0]


@tool
def get_information_for_question_answering(user_query: Query, source: Source | None = None) -> str:
    """Search MongoDB documentation chunks. An optional exact source filename narrows the retrieved candidates."""
    t0 = time.perf_counter()
    vec = generate_embedding(user_query)
    top_k = settings.retrieval_top_k
    candidate_limit = top_k * 4
    candidates = vector_search(db()["chunked_docs"], settings, vec, limit=candidate_limit, source=source)
    docs, seen = [], set()
    for candidate in candidates:
        text = " ".join(candidate.get("body", "").split())
        if not text or text in seen:
            continue
        seen.add(text)
        docs.append(candidate)
        if len(docs) == top_k:
            break
    emit("db_operation", node="tools", collection="chunked_docs", op="$vectorSearch",
         index=settings.vector_index, limit=top_k, candidate_limit=candidate_limit, min_score=settings.vector_min_score,
         source_filter=source, candidates_returned=len(candidates), returned=len(docs),
         doc_ids=[str(d["_id"]) for d in docs], titles=[d.get("title") for d in docs],
         scores=[round(d["score"], 4) for d in docs],
         latency_ms=round((time.perf_counter() - t0) * 1000, 1))
    if not docs:
        return "No relevant documents found."
    return "\n\n".join(cite_document(d, "chunked_docs", settings.retrieval_chunk_chars) for d in docs)


@tool
def get_page_content_for_summarization(user_query: Title) -> str:
    """Retrieve a full documentation page by its exact title for summarization."""
    t0 = time.perf_counter()
    doc = db()["full_docs"].find_one({"title": user_query}, {"title": 1, "body": 1, "source": 1})
    emit("db_operation", node="tools", collection="full_docs", op="find_one",
         filter={"title": user_query}, returned=1 if doc else 0,
         doc_ids=[str(doc["_id"])] if doc else [],
         latency_ms=round((time.perf_counter() - t0) * 1000, 1))
    if not doc:
        return "Document not found"
    return cite_document(doc, "full_docs", settings.full_document_chars)


TOOLS = [get_information_for_question_answering, get_page_content_for_summarization]
