"""Ingest your own .md/.txt files into full_docs and chunked_docs (idempotent by title+hash).
Usage: python scripts/ingest_documents.py ./my_docs
The official course dataset is NOT bundled; this script ingests whatever you provide."""
import hashlib, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import voyageai
from app.config import settings
from app.mongo import db

CHUNK, OVERLAP = 1200, 150


def chunks(text):
    i = 0
    while i < len(text):
        yield text[i:i + CHUNK]
        i += CHUNK - OVERLAP


def main(folder):
    vo = voyageai.Client(api_key=settings.voyage_api_key)
    full, chunked = db()["full_docs"], db()["chunked_docs"]
    for name in sorted(os.listdir(folder)):
        if not name.endswith((".md", ".txt")):
            continue
        body = open(os.path.join(folder, name), encoding="utf-8").read()
        title, h = os.path.splitext(name)[0], hashlib.sha256(body.encode()).hexdigest()
        if full.find_one({"title": title, "hash": h}):
            print("skip (unchanged):", title)
            continue
        full.replace_one({"title": title}, {"title": title, "body": body, "hash": h, "source": name}, upsert=True)
        chunked.delete_many({"title": title})
        parts = list(chunks(body))
        embs = vo.embed(parts, model=settings.embedding_model, input_type="document").embeddings
        assert all(len(e) == settings.embedding_dims for e in embs), "embedding dimension mismatch"
        chunked.insert_many([{"title": title, "body": p, "embedding": e, "source": name} for p, e in zip(parts, embs)])
        print(f"ingested {title}: {len(parts)} chunks")


if __name__ == "__main__":
    main(sys.argv[1])
