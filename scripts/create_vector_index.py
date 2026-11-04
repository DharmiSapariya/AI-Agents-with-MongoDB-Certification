"""Create the Atlas Vector Search index on chunked_docs.embedding (512 dims, cosine)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from pymongo.operations import SearchIndexModel
from app.config import settings
from app.mongo import db

col = db()["chunked_docs"]
model = SearchIndexModel(name=settings.vector_index, type="vectorSearch", definition={
    "fields": [{"type": "vector", "path": "embedding",
                "numDimensions": settings.embedding_dims, "similarity": "cosine"}]})
print("Created:", col.create_search_index(model=model))
