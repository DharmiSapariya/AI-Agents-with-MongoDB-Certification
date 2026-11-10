from unittest.mock import Mock

import pytest
from scripts import create_vector_index

from app.config import Settings
from app.retrieval import VectorIndexUnavailable, vector_index_definition, vector_search


@pytest.fixture
def config():
    return Settings(_env_file=None, app_mode="demo", vector_min_score=0.7)


def atlas_index(config, **overrides):
    return {
        "type": "vectorSearch", "status": "READY", "queryable": True,
        "latestDefinition": vector_index_definition(config), **overrides,
    }


@pytest.mark.parametrize("status", ["missing", "building", "incompatible", "failed"])
def test_vector_search_requires_ready_compatible_index(config, status):
    overrides = {
        "building": {"status": "BUILDING", "queryable": False},
        "incompatible": {"latestDefinition": {"fields": []}},
        "failed": {"status": "FAILED", "queryable": False},
    }
    collection = Mock()
    collection.list_search_indexes.return_value = (
        [] if status == "missing" else [atlas_index(config, **overrides[status])]
    )
    with pytest.raises(VectorIndexUnavailable, match=status):
        vector_search(collection, config, [0.0] * config.embedding_dims)
    collection.aggregate.assert_not_called()


def test_vector_search_keeps_matches_at_threshold_with_source_metadata(config):
    collection = Mock()
    collection.list_search_indexes.return_value = [atlas_index(config)]
    match = {"_id": "match", "source": "example.md", "chunk_index": 0, "score": 0.7}
    collection.aggregate.return_value = [match, {"_id": "miss", "score": 0.69}]
    query = [0.0] * config.embedding_dims
    assert vector_search(collection, config, query) == [match]
    pipeline = collection.aggregate.call_args.args[0]
    assert pipeline[0]["$vectorSearch"]["queryVector"] == query
    assert pipeline[1]["$project"]["source"] == 1


def test_index_setup_creates_once_and_waits_for_ready(config, monkeypatch):
    monkeypatch.setattr(create_vector_index, "sleep", lambda _: None)
    collection = Mock()
    collection.list_search_indexes.side_effect = [
        [], [atlas_index(config, status="BUILDING")], [atlas_index(config)], [atlas_index(config)],
    ]
    create_vector_index.ensure_index(collection, config, 10)
    create_vector_index.ensure_index(collection, config, 10)
    collection.create_search_index.assert_called_once()
    assert collection.create_search_index.call_args.kwargs["model"].document["definition"] == (
        vector_index_definition(config)
    )


def test_index_setup_times_out_while_building(config, monkeypatch):
    monkeypatch.setattr(create_vector_index, "monotonic", Mock(side_effect=[0, 10]))
    collection = Mock()
    collection.list_search_indexes.return_value = [atlas_index(config, status="BUILDING")]
    with pytest.raises(TimeoutError, match="building"):
        create_vector_index.ensure_index(collection, config, 10)
    collection.create_search_index.assert_not_called()


def test_retrieval_metrics_use_unique_matches_and_exclude_unanswerable_cases():
    from scripts.evaluate_retrieval import evaluate

    responses = iter([["wrong", "right", "right"], [], ["wrong"]])
    cases = [
        {"id": "partial", "query": "first", "expected_sources": ["right", "another"]},
        {"id": "miss", "query": "second", "expected_sources": ["right"]},
        {"id": "outside", "query": "third", "expected_sources": []},
    ]
    result = evaluate(cases, lambda _: next(responses))
    assert result["recall_at_k"] == 0.25
    assert result["mrr_at_k"] == 0.25
    assert result["answerable_count"] == 2
    assert result["cases"][2]["returned_no_evidence"] is False
    assert result["cases"][2]["recall"] is None


def test_failed_cases_stay_in_the_benchmark_denominator(tmp_path):
    import json

    from scripts.evaluate_retrieval import evaluate, save_report

    from app.errors import EmbeddingError

    def failed(_query):
        raise EmbeddingError("private provider detail")

    rows = [{"id": "case", "query": "test", "expected_sources": ["wanted"]}]
    report = {"run_id": "example", **evaluate(rows, failed, capture_failures=True)}
    assert report["failed_cases"] == 1 and report["recall_at_k"] == 0
    assert report["cases"][0]["error"] == "embedding_provider_error"
    saved = save_report(tmp_path, report)
    assert json.loads(saved.read_text()) == report
    assert "private provider detail" not in saved.read_text()
    with pytest.raises(FileExistsError):
        save_report(tmp_path, report)


def test_source_filter_is_scalar_and_applied_after_vector_search(config):
    collection = Mock()
    collection.list_search_indexes.return_value = [atlas_index(config)]
    collection.aggregate.return_value = []
    vector_search(collection, config, [0.0] * config.embedding_dims, source="manual.md")
    pipeline = collection.aggregate.call_args.args[0]
    assert "$vectorSearch" in pipeline[0]
    assert pipeline[1] == {"$match": {"source": "manual.md"}}


def test_precision_penalizes_duplicate_and_missing_slots():
    from scripts.evaluate_retrieval import evaluate

    cases = [{"id": "q", "query": "query", "expected_sources": ["a", "b"]}]
    result = evaluate(cases, lambda _: ["a", "a", "irrelevant", "b"], top_k=3)
    assert result["recall_at_k"] == 0.5
    assert result["precision_at_k"] == 1 / 3
    assert result["mean_duplicate_source_rate"] == 1 / 3
