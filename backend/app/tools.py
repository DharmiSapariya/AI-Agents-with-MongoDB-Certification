"""The two course tools (faithful to the official lesson) plus tracing and prompt-injection framing."""
import html
import re
import time

from langchain_core.tools import tool

from .config import settings
from .embeddings import VoyageEmbeddingProvider
from .mongo import db
from .retrieval import vector_search
from .tracing import CURRENT, emit

_WRAPPER_TAG = re.compile(r"<(\s*/?\s*retrieved_document)", re.I)


def wrap_document(title: str, body: str, citation_id: str = "") -> str:
    """Wrap retrieved text as untrusted data; a document cannot close the wrapper early."""
    safe_body = _WRAPPER_TAG.sub(r"&lt;\1", body)
    citation = f' citation="{citation_id}"' if citation_id else ""
    return f'<retrieved_document{citation} title="{html.escape(title, quote=True)}">\n{safe_body}\n</retrieved_document>'


def cite_document(doc: dict, collection: str) -> str:
    tracer = CURRENT.get()
    citation_id = ""
    if tracer is not None:
        citation_id = f"S-{tracer.execution_id}-{len(tracer.sources) + 1}"
        tracer.sources[citation_id] = {
            "id": citation_id, "document_id": str(doc["_id"]), "collection": collection,
            "title": doc.get("title", "unknown"), "source": doc.get("source"),
            "chunk_index": doc.get("chunk_index"),
        }
    return wrap_document(doc.get("title", "unknown"), doc.get("body", ""), citation_id)


def generate_embedding(text: str) -> list[float]:
    return VoyageEmbeddingProvider(settings).embed([text], "query")[0]


@tool
def get_information_for_question_answering(user_query: str) -> str:
    """Retrieve relevant MongoDB documentation chunks for a question using Atlas Vector Search."""
    t0 = time.perf_counter()
    vec = generate_embedding(user_query)
    docs = vector_search(db()["chunked_docs"], settings, vec)
    emit("db_operation", node="tools", collection="chunked_docs", op="$vectorSearch",
         index=settings.vector_index, limit=5, num_candidates=150, min_score=settings.vector_min_score, returned=len(docs),
         doc_ids=[str(d["_id"]) for d in docs], titles=[d.get("title") for d in docs],
         scores=[round(d["score"], 4) for d in docs],
         latency_ms=round((time.perf_counter() - t0) * 1000, 1))
    if not docs:
        return "No relevant documents found."
    return "\n\n".join(cite_document(d, "chunked_docs") for d in docs)


@tool
def get_page_content_for_summarization(user_query: str) -> str:
    """Retrieve a full documentation page by its exact title for summarization."""
    t0 = time.perf_counter()
    doc = db()["full_docs"].find_one({"title": user_query}, {"title": 1, "body": 1, "source": 1})
    emit("db_operation", node="tools", collection="full_docs", op="find_one",
         filter={"title": user_query}, returned=1 if doc else 0,
         doc_ids=[str(doc["_id"])] if doc else [],
         latency_ms=round((time.perf_counter() - t0) * 1000, 1))
    if not doc:
        return "Document not found"
    return cite_document(doc, "full_docs")


TOOLS = [get_information_for_question_answering, get_page_content_for_summarization]
