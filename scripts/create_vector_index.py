"""Create or verify the configured Atlas Vector Search index."""
import argparse
import os
import sys
from time import monotonic, sleep

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from pymongo.errors import PyMongoError
from pymongo.operations import SearchIndexModel

from app.config import Settings, settings
from app.mongo import DatabaseNotConfigured, close, db
from app.retrieval import index_state, vector_index_definition


def ensure_index(collection, config: Settings, wait_seconds: int) -> None:
    state = index_state(collection, config)
    if state == "missing":
        collection.create_search_index(model=SearchIndexModel(
            name=config.vector_index, type="vectorSearch", definition=vector_index_definition(config),
        ))
    deadline = monotonic() + wait_seconds
    while state != "ready":
        if state in {"incompatible", "failed"}:
            raise ValueError(f"Index is {state}; inspect it in Atlas before making changes.")
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Index is {state}; rerun this command to check again.")
        sleep(min(2, remaining))
        state = index_state(collection, config)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-seconds", type=int, default=120)
    args = parser.parse_args()
    if args.wait_seconds < 1:
        parser.error("--wait-seconds must be positive")
    try:
        ensure_index(db()["chunked_docs"], settings, args.wait_seconds)
    except (ValueError, TimeoutError) as exc:
        sys.exit(str(exc))
    except (DatabaseNotConfigured, PyMongoError) as exc:
        sys.exit(f"Atlas index command failed ({type(exc).__name__}); check connectivity and permissions.")
    finally:
        close()
    print(f"Ready: {settings.vector_index}")


if __name__ == "__main__":
    main()
