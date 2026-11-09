"""Ingest .md/.txt files from a folder into full_docs and chunked_docs.

Usage: python scripts/ingest_documents.py ./my_docs
The official course dataset is not bundled; this ingests whatever you provide.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.config import settings
from app.embeddings import EmbeddingProvider, VoyageEmbeddingProvider
from app.ingest import ingest_document
from app.mongo import db


def main(folder: str) -> None:
    provider: EmbeddingProvider = VoyageEmbeddingProvider(settings)

    def embed(texts):
        return provider.embed(texts, "document")

    full, chunked = db()["full_docs"], db()["chunked_docs"]
    for name in sorted(os.listdir(folder)):
        if not name.endswith((".md", ".txt")):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            body = f.read()
        title = os.path.splitext(name)[0]
        status = ingest_document(full, chunked, embed, title, body, name, settings.embedding_dims)
        print(f"{status}: {title}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
