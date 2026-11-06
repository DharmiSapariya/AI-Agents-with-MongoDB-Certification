"""Document ingestion into full_docs and chunked_docs.

Chunks are embedded before anything is written, and the full_docs record (which holds the
hash used for the "unchanged" check) is written last. A failure part-way through therefore
leaves the document eligible for re-ingestion instead of looking complete.
"""
import hashlib
from typing import Callable, Iterator, Sequence

EMBED_BATCH = 64
Embedder = Callable[[Sequence[str]], list[list[float]]]


def split_text(text: str, size: int = 1200, overlap: int = 150) -> Iterator[str]:
    if overlap >= size:
        raise ValueError("overlap must be smaller than chunk size")
    for start in range(0, len(text), size - overlap):
        yield text[start:start + size]
        if start + size >= len(text):
            break


def embed_all(embed: Embedder, parts: list[str], dims: int) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(parts), EMBED_BATCH):
        vectors.extend(embed(parts[i:i + EMBED_BATCH]))
    if len(vectors) != len(parts):
        raise ValueError(f"expected {len(parts)} embeddings, got {len(vectors)}")
    bad = [i for i, v in enumerate(vectors) if len(v) != dims]
    if bad:
        raise ValueError(f"embedding dimension mismatch (expected {dims}) in chunks {bad[:5]}")
    return vectors


def ingest_document(full, chunked, embed: Embedder, title: str, body: str, source: str,
                    dims: int, size: int = 1200, overlap: int = 150) -> str:
    """Returns 'skipped', 'empty' or 'ingested'."""
    if not body.strip():
        return "empty"
    digest = hashlib.sha256(body.encode()).hexdigest()
    existing = full.find_one({"title": title, "hash": digest})
    if existing and chunked.count_documents({"title": title}) == existing.get("chunk_count"):
        return "skipped"

    parts = list(split_text(body, size, overlap))
    vectors = embed_all(embed, parts, dims)
    chunked.delete_many({"title": title})
    chunked.insert_many([{"title": title, "body": p, "embedding": v, "source": source, "chunk_index": i}
                         for i, (p, v) in enumerate(zip(parts, vectors, strict=True))])
    full.replace_one({"title": title}, {"title": title, "body": body, "hash": digest,
                                        "source": source, "chunk_count": len(parts)}, upsert=True)
    return "ingested"
