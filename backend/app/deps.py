"""Shared FastAPI dependencies."""
from . import mongo


def db_provider():
    """Return a zero-argument callable that yields the database.

    Routes call it only after their config and authorization checks, so a missing database
    cannot mask a validation or auth error. Tests override it with app.dependency_overrides.
    """
    return mongo.db
