"""The two course tools (faithful to the official lesson) plus tracing and prompt-injection framing."""
import html
import re
import time
from typing import List

from langchain_core.tools import tool

from .config import settings
from .errors import EmbeddingError
from .mongo import db
from .tracing import emit

_WRAPPER_TAG = re.compile(r"<(\s*/?\s*retrieved_document)", re.I)


def wrap_document(title: str, body: str) -> str:
    """Wrap retrieved text as untrusted data; a document cannot close the wrapper early."""
    safe_body = _WRAPPER_TAG.sub(r"&lt;\1", body)
    return f'<retrieved_document title="{html.escape(title, quote=True)}">\n{safe_body}\n</retrieved_document>'


def generate_embedding(text: str) -> List[float]:
    import voyageai
    try:
        c = voyageai.Client(api_key=settings.voyage_api_key, max_retries=settings.embedding_max_retries,
                            timeout=settings.embedding_timeout_s)
        result = c.embed([text], model=settings.embedding_model, input_type="query")
    except Exception as exc:
        raise EmbeddingError() from exc
    return [float(x) for x in result.embeddings[0]]


@tool
def get_information_for_question_answering(user_query: str) -> str:
    """Retrieve relevant MongoDB documentation chunks for a question using Atlas Vector Search."""
    t0 = time.perf_counter()
    vec = generate_embedding(user_query)
    pipeline = [
        {"$vectorSearch": {"index": settings.vector_index, "path": "embedding",
                           "queryVector": vec, "numCandidates": 150, "limit": 5}},
        {"$project": {"_id": 1, "title": 1, "body": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]
    docs = list(db()["chunked_docs"].aggregate(pipeline))
    emit("db_operation", node="tools", collection="chunked_docs", op="$vectorSearch",
         index=settings.vector_index, limit=5, num_candidates=150, returned=len(docs),
         doc_ids=[str(d["_id"]) for d in docs], titles=[d.get("title") for d in docs],
         scores=[round(d["score"], 4) for d in docs],
         latency_ms=round((time.perf_counter() - t0) * 1000, 1))
    if not docs:
        return "No relevant documents found."
    return "\n\n".join(wrap_document(d.get("title", "unknown"), d.get("body", "")) for d in docs)


@tool
def get_page_content_for_summarization(user_query: str) -> str:
    """Retrieve a full documentation page by its exact title for summarization."""
    t0 = time.perf_counter()
    doc = db()["full_docs"].find_one({"title": user_query}, {"title": 1, "body": 1})
    emit("db_operation", node="tools", collection="full_docs", op="find_one",
         filter={"title": user_query}, returned=1 if doc else 0,
         doc_ids=[str(doc["_id"])] if doc else [],
         latency_ms=round((time.perf_counter() - t0) * 1000, 1))
    if not doc:
        return "Document not found"
    return wrap_document(doc["title"], doc["body"])


TOOLS = [get_information_for_question_answering, get_page_content_for_summarization]
