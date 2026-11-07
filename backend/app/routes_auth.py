"""Account routes: register, login, current user."""
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator

from . import auth
from .deps import db_provider

router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(auth.require_auth_enabled)])


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=auth.PASSWORD_MIN, max_length=auth.PASSWORD_MAX)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        email = auth.normalize_email(v)
        if email is None:
            raise ValueError("must be a valid ASCII email address")
        return email


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=auth.PASSWORD_MAX)


# Plain `def` routes run in FastAPI's threadpool, so Argon2 and PyMongo never block the event loop.
@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=auth.PublicUser)
def register(body: RegisterIn, get_db=Depends(db_provider)):
    return auth.to_public(auth.create_user(get_db(), body.email, body.password))


@router.post("/login", response_model=auth.TokenOut)
def login(body: LoginIn, get_db=Depends(db_provider)):
    user = auth.authenticate(get_db(), body.email, body.password)
    return auth.issue_token(user["_id"])


@router.get("/me", response_model=auth.PublicUser)
def me(user: auth.CurrentUser):
    return auth.to_public(user)
