"""Accounts, Argon2id password hashing and signed access tokens.

Email rule: ASCII only, trimmed and lowercased; registration and login use the same function.
Passwords are 12-128 characters, hashed as given (no truncation, no normalization).
Tokens are HS256 JWTs with iss, aud, sub, iat, nbf, exp and jti, all required on decode.
"""
import logging
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from .config import settings
from .deps import db_provider
from .errors import AuthenticationError, AuthUnavailable, EmailTaken, InvalidCredentials
from .logging_config import log

logger = logging.getLogger("app.auth")

ALGORITHM = "HS256"
PASSWORD_MIN, PASSWORD_MAX = 12, 128
REQUIRED_CLAIMS = ["exp", "iat", "nbf", "sub", "iss", "aud", "jti"]
EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]{1,64}@(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")

_hasher = PasswordHasher()  # argon2-cffi defaults: Argon2id, m=64 MiB, t=3, p=4
# Hash of a random value nobody knows, made with the parameters above. Logins for unknown emails verify
# against it so they cost the same as a wrong password, with no warm-up step to forget.
# If the parameters change, regenerate it (a test checks they still match).
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$NE9/WXnwfX8VD7gDHN00sA$bNarqTxykGJ/hxqoUt4zbUdzG1770wJm7GRIZ1vDa4E"
_hash_slots = threading.BoundedSemaphore(settings.auth_max_concurrent_hashes)
_bearer = HTTPBearer(auto_error=False)


class PublicUser(BaseModel):
    id: str
    email: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def normalize_email(raw: str) -> str | None:
    """Return the canonical email, or None if it is not acceptable."""
    if not raw.isascii():
        return None
    email = raw.strip().lower()
    return email if len(email) <= 254 and EMAIL_RE.match(email) else None


def hash_password(password: str) -> str:
    with _hash_slots:  # caps concurrent 64 MiB hashes until request rate limits exist
        return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    with _hash_slots:
        try:
            return _hasher.verify(stored_hash, password)
        except (VerificationError, InvalidHashError):
            return False


def to_public(user: dict[str, Any]) -> PublicUser:
    return PublicUser(id=user["_id"], email=user["email"], created_at=user["created_at"])


def create_user(database, email: str, password: str) -> dict[str, Any]:
    database["users"].create_index("email", unique=True, name="email_unique")  # idempotent
    user = {"_id": uuid.uuid4().hex, "email": email, "password_hash": hash_password(password),
            "created_at": datetime.now(timezone.utc)}
    try:
        database["users"].insert_one(dict(user))
    except DuplicateKeyError:
        raise EmailTaken() from None
    log(logger, logging.INFO, "user_registered", user_id=user["_id"])
    return user


def authenticate(database, raw_email: str, password: str) -> dict[str, Any]:
    """Check credentials. Unknown email and wrong password cost one verification each and fail identically."""
    email = normalize_email(raw_email)
    user = database["users"].find_one({"email": email}) if email else None
    verified = verify_password(user["password_hash"] if user else DUMMY_HASH, password)
    if user is None or not verified:
        reason = "invalid_email" if email is None else "unknown_user" if user is None else "bad_password"
        log(logger, logging.INFO, "login_failed", reason=reason)
        raise InvalidCredentials()
    log(logger, logging.INFO, "login_succeeded", user_id=user["_id"])
    return user


def issue_token(user_id: str, now: datetime | None = None) -> TokenOut:
    now = now or datetime.now(timezone.utc)
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    claims = {"iss": settings.jwt_issuer, "aud": settings.jwt_audience, "sub": user_id, "iat": now, "nbf": now,
              "exp": now + ttl, "jti": uuid.uuid4().hex}
    token = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)
    return TokenOut(access_token=token, expires_in=int(ttl.total_seconds()))


def decode_token(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=[ALGORITHM],
                            audience=settings.jwt_audience, issuer=settings.jwt_issuer,
                            options={"require": REQUIRED_CLAIMS})
    except jwt.InvalidTokenError as exc:
        log(logger, logging.INFO, "token_rejected", reason=type(exc).__name__)
        raise _invalid_token() from None
    if not isinstance(claims["sub"], str):
        raise _invalid_token()
    return claims


def _invalid_token() -> AuthenticationError:
    return AuthenticationError(invalid=True, code="invalid_token", message="Invalid or expired access token.")


def require_auth_enabled() -> None:
    if not settings.auth_enabled:
        raise AuthUnavailable(f"Authentication is unavailable: {settings.auth_unavailable_reason}.")


def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
                     get_db=Depends(db_provider)) -> dict[str, Any]:
    """Resolve the bearer token to a stored user. Missing user, bad token and expiry look the same to clients."""
    require_auth_enabled()
    if credentials is None:
        raise AuthenticationError(invalid=False, code="not_authenticated", message="Authentication required.")
    claims = decode_token(credentials.credentials)
    user = get_db()["users"].find_one({"_id": claims["sub"]})
    if user is None:
        log(logger, logging.INFO, "token_rejected", reason="unknown_subject")
        raise _invalid_token()
    return user


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
