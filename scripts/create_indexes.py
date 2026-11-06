"""Create the regular MongoDB indexes (run once; safe to repeat). Vector index: create_vector_index.py."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.indexes import ensure_indexes
from app.mongo import db

for name in ensure_indexes(db()):
    print("index:", name)
