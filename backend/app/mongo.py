from functools import lru_cache
from pymongo import MongoClient
from .config import settings


@lru_cache(maxsize=1)
def client() -> MongoClient:
    return MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=settings.mongo_timeout_ms)


def db():
    return client()[settings.db_name]
