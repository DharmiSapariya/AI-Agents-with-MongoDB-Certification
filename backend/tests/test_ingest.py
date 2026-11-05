import mongomock
import pytest

from app.ingest import embed_all, ingest_document, split_text

DIMS = 4


def good_embed(texts):
    return [[0.1] * DIMS for _ in texts]


@pytest.fixture
def cols():
    db = mongomock.MongoClient()["t"]
    return db["full_docs"], db["chunked_docs"]


def test_split_covers_text_with_overlap():
    text = "".join(chr(97 + i % 26) for i in range(2500))
    parts = list(split_text(text, 1000, 100))
    assert parts[0][-100:] == parts[1][:100]
    assert len(parts[-1]) > 0 and text.endswith(parts[-1])


def test_split_rejects_bad_overlap():
    with pytest.raises(ValueError):
        list(split_text("abc", 10, 10))


def test_embed_all_batches_and_validates_dimensions():
    calls = []

    def embed(batch):
        calls.append(len(batch))
        return [[0.0] * DIMS for _ in batch]

    assert len(embed_all(embed, ["x"] * 150, DIMS)) == 150
    assert calls == [64, 64, 22]
    with pytest.raises(ValueError, match="dimension"):
        embed_all(lambda b: [[0.0] * 3 for _ in b], ["x"], DIMS)


def test_ingest_then_skip_unchanged(cols):
    full, chunked = cols
    assert ingest_document(full, chunked, good_embed, "Doc", "hello " * 400, "doc.md", DIMS) == "ingested"
    assert chunked.count_documents({"title": "Doc"}) == full.find_one({"title": "Doc"})["chunk_count"]
    assert ingest_document(full, chunked, good_embed, "Doc", "hello " * 400, "doc.md", DIMS) == "skipped"


def test_embedding_failure_leaves_existing_data_and_allows_retry(cols):
    full, chunked = cols
    ingest_document(full, chunked, good_embed, "Doc", "old " * 50, "doc.md", DIMS)

    def broken(_):
        raise RuntimeError("provider down")

    with pytest.raises(RuntimeError):
        ingest_document(full, chunked, broken, "Doc", "new " * 50, "doc.md", DIMS)
    assert chunked.find_one({"title": "Doc"})["body"].startswith("old")
    assert full.find_one({"title": "Doc"})["body"].startswith("old")
    assert ingest_document(full, chunked, good_embed, "Doc", "new " * 50, "doc.md", DIMS) == "ingested"


def test_missing_chunks_are_not_treated_as_unchanged(cols):
    full, chunked = cols
    ingest_document(full, chunked, good_embed, "Doc", "text " * 300, "doc.md", DIMS)
    chunked.delete_many({"title": "Doc"})
    assert ingest_document(full, chunked, good_embed, "Doc", "text " * 300, "doc.md", DIMS) == "ingested"


def test_empty_file_is_skipped(cols):
    full, chunked = cols
    assert ingest_document(full, chunked, good_embed, "Empty", "  \n", "e.md", DIMS) == "empty"
    assert full.count_documents({}) == 0
