"""Evaluate the live Voyage and Atlas retrieval path using a versioned corpus."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from pymongo.errors import PyMongoError

from app.config import settings
from app.embeddings import VoyageEmbeddingProvider
from app.errors import ApiError, classify
from app.mongo import close, db
from app.retrieval import vector_search

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks" / "retrieval" / "cases.json"


def evaluate(cases, retrieve, *, top_k=5, capture_failures=False):
    results = []
    for case in cases:
        start = perf_counter()
        expected = set(case["expected_sources"])
        error = None
        try:
            sources = retrieve(case["query"])[:top_k]
        except Exception as exc:
            if not capture_failures:
                raise
            error = classify(exc).code
            sources = []
        relevant = expected.intersection(sources)
        named_sources = [source for source in sources if source is not None]
        ranks = [rank for rank, source in enumerate(sources, start=1) if source in expected]
        results.append({
            "id": case["id"], "expected_sources": sorted(expected), "retrieved_sources": sources,
            "recall": len(relevant) / len(expected) if expected else None,
            "precision_at_k": len(relevant) / top_k if expected else None,
            "duplicate_source_rate": (len(named_sources) - len(set(named_sources))) / len(named_sources)
            if named_sources else None,
            "reciprocal_rank": (1 / ranks[0] if ranks else 0.0) if expected else None,
            "returned_no_evidence": not sources if error is None else None, "error": error, "latency_ms": round((perf_counter() - start) * 1000, 2),
        })
    answerable = [result for result in results if result["recall"] is not None]
    duplicate_rates = [row["duplicate_source_rate"] for row in results if row["duplicate_source_rate"] is not None]
    return {
        "case_count": len(results), "answerable_count": len(answerable),
        "failed_cases": sum(result["error"] is not None for result in results),
        "recall_at_k": sum(row["recall"] for row in answerable) / len(answerable) if answerable else None,
        "precision_at_k": sum(row["precision_at_k"] for row in answerable) / len(answerable) if answerable else None,
        "mean_duplicate_source_rate": sum(duplicate_rates) / len(duplicate_rates) if duplicate_rates else None,
        "mrr_at_k": sum(row["reciprocal_rank"] for row in answerable) / len(answerable) if answerable else None,
        "cases": results,
    }


def revision() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL,
                                       text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def save_report(directory: Path, report: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report['run_id']}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--strategy", choices=("vector", "agent"), default="vector")
    parser.add_argument("--output-dir", type=Path, help="Save a separate JSON report for this run.")
    parser.add_argument("--allow-agent-writes", action="store_true",
                        help="Confirm the agent is using isolated data and checkpoint databases.")
    args = parser.parse_args()
    if not 1 <= args.top_k <= 100:
        parser.error("--top-k must be between 1 and 100")
    if not settings.mongodb_uri or not settings.voyage_api_key:
        parser.error("MONGODB_URI and VOYAGE_API_KEY are required for live evaluation")
    if args.strategy == "agent" and (not settings.openai_api_key or not args.allow_agent_writes):
        parser.error("Agent evaluation needs OPENAI_API_KEY and --allow-agent-writes on an isolated database.")
    dataset_bytes = args.dataset.read_bytes()
    dataset = json.loads(dataset_bytes)
    provider = VoyageEmbeddingProvider(settings)
    database = db()

    def retrieve_vector(query):
        vector = provider.embed([query], "query")[0]
        rows = vector_search(database["chunked_docs"], settings, vector, limit=args.top_k)
        return [row.get("source") for row in rows]

    def retrieve_agent(query):
        from app.graph import run

        result = run(f"benchmark_{uuid4().hex}", query)
        if result["outcome"] == "retrieval_failed":
            raise ApiError("A benchmark retrieval tool failed.", code="retrieval_failed")
        return [item.get("source") for item in result["citations"][:args.top_k]]

    try:
        for source in {source for case in dataset["cases"] for source in case["expected_sources"]}:
            if not database["full_docs"].find_one({"source": source}, {"_id": 1}):
                sys.exit(f"Missing corpus source: {source}. Ingest the evaluation corpus first.")
        retrieve = retrieve_vector if args.strategy == "vector" else retrieve_agent
        report = evaluate(dataset["cases"], retrieve, top_k=args.top_k, capture_failures=True)
    except (ApiError, PyMongoError) as exc:
        sys.exit(f"Live evaluation failed ({getattr(exc, 'code', None) or type(exc).__name__}).")
    finally:
        close()
    report = {
        "mode": "live_atlas", "strategy": args.strategy, "report_version": 1,
        "run_id": uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": revision(), "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "dataset_version": dataset["version"], "top_k": args.top_k,
        "llm_model": settings.llm_model if args.strategy == "agent" else None,
        "model": settings.embedding_model, "dimensions": settings.embedding_dims,
        "index": settings.vector_index, "min_score": settings.vector_min_score, **report,
    }
    if args.output_dir:
        path = save_report(args.output_dir, report)
        print(f"Saved report: {path}", file=sys.stderr)
    print(json.dumps(report, indent=2))
    if report["failed_cases"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
