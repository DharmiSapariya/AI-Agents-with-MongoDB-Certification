"""Evaluate the live Voyage and Atlas retrieval path using a versioned corpus."""
import argparse
import json
import os
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from pymongo.errors import PyMongoError

from app.config import settings
from app.embeddings import VoyageEmbeddingProvider
from app.errors import ApiError
from app.mongo import close, db
from app.retrieval import vector_search

DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "retrieval" / "cases.json"


def evaluate(cases, retrieve):
    results = []
    for case in cases:
        start = perf_counter()
        expected = set(case["expected_sources"])
        sources = retrieve(case["query"])
        ranks = [rank for rank, source in enumerate(sources, start=1) if source in expected]
        results.append({
            "id": case["id"], "expected_sources": sorted(expected), "retrieved_sources": sources,
            "recall": len(expected.intersection(sources)) / len(expected) if expected else None,
            "reciprocal_rank": (1 / ranks[0] if ranks else 0.0) if expected else None,
            "returned_no_evidence": not sources, "latency_ms": round((perf_counter() - start) * 1000, 2),
        })
    answerable = [result for result in results if result["recall"] is not None]
    return {
        "case_count": len(results), "answerable_count": len(answerable),
        "recall_at_k": sum(row["recall"] for row in answerable) / len(answerable) if answerable else None,
        "mrr_at_k": sum(row["reciprocal_rank"] for row in answerable) / len(answerable) if answerable else None,
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 100:
        parser.error("--top-k must be between 1 and 100")
    if not settings.mongodb_uri or not settings.voyage_api_key:
        parser.error("MONGODB_URI and VOYAGE_API_KEY are required for live evaluation")
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    provider = VoyageEmbeddingProvider(settings)
    database = db()

    def retrieve(query):
        vector = provider.embed([query], "query")[0]
        rows = vector_search(database["chunked_docs"], settings, vector, limit=args.top_k)
        return [row.get("source") for row in rows]

    try:
        for source in {source for case in dataset["cases"] for source in case["expected_sources"]}:
            if not database["full_docs"].find_one({"source": source}, {"_id": 1}):
                sys.exit(f"Missing corpus source: {source}. Ingest the evaluation corpus first.")
        report = evaluate(dataset["cases"], retrieve)
    except (ApiError, PyMongoError) as exc:
        sys.exit(f"Live evaluation failed ({getattr(exc, 'code', None) or type(exc).__name__}).")
    finally:
        close()
    print(json.dumps({
        "mode": "live_atlas", "dataset_version": dataset["version"], "top_k": args.top_k,
        "model": settings.embedding_model, "dimensions": settings.embedding_dims,
        "index": settings.vector_index, "min_score": settings.vector_min_score, **report,
    }, indent=2))


if __name__ == "__main__":
    main()
