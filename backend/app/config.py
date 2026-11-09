"""Environment-based configuration, validated once at startup.

APP_MODE=auto (default) runs live when MongoDB, OpenAI and Voyage are all configured and demo
otherwise. APP_MODE=live refuses to start unless everything is configured and valid.
APP_MODE=demo never talks to external services, even if credentials are present.
Error messages name the offending variable, never its value.
"""
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Output dimensions the Voyage models support by default; unknown models are not checked.
KNOWN_EMBEDDING_DIMS = {"voyage-3-lite": {512}, "voyage-3": {1024}}


class ConfigError(RuntimeError):
    """Invalid configuration. The message never contains a setting's value."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: Literal["auto", "demo", "live"] = "auto"
    mongodb_uri: str = ""
    openai_api_key: str = ""
    voyage_api_key: str = ""
    db_name: str = Field("ai_agents", min_length=1, max_length=63, pattern=r"^[A-Za-z0-9_\-]+$")
    checkpoint_db: str = Field("checkpointing_db", min_length=1, max_length=63, pattern=r"^[A-Za-z0-9_\-]+$")
    llm_model: str = Field("gpt-4o", min_length=1)
    embedding_model: str = Field("voyage-3-lite", min_length=1)
    embedding_dims: int = Field(512, ge=1, le=4096)
    vector_index: str = Field("vector_index", min_length=1)
    max_graph_steps: int = Field(12, ge=2, le=50)
    mongo_timeout_ms: int = Field(5000, ge=500, le=60000)
    mongo_socket_timeout_ms: int = Field(30000, ge=1000, le=300000)
    mongo_max_pool_size: int = Field(20, ge=1, le=200)
    llm_timeout_s: float = Field(30, gt=0, le=300)
    llm_max_retries: int = Field(2, ge=0, le=5)
    embedding_timeout_s: float = Field(15, gt=0, le=120)
    embedding_max_retries: int = Field(2, ge=0, le=5)
    jwt_secret: SecretStr = SecretStr("")
    jwt_issuer: str = Field("mongodb-ai-agent-platform", min_length=1)
    jwt_audience: str = Field("mongodb-ai-agent-platform-api", min_length=1)
    access_token_ttl_minutes: int = Field(30, ge=1, le=1440)
    auth_max_concurrent_hashes: int = Field(4, ge=1, le=32)
    rate_limit_enabled: bool = True
    rate_register_ip_per_hour: int = Field(10, ge=1, le=100000)
    rate_login_ip_per_min: int = Field(10, ge=1, le=100000)
    rate_chat_ip_per_min: int = Field(30, ge=1, le=100000)
    rate_chat_user_per_min: int = Field(10, ge=1, le=100000)
    rate_read_ip_per_min: int = Field(120, ge=1, le=100000)
    rate_limit_max_keys: int = Field(10000, ge=100, le=1000000)
    max_body_bytes: int = Field(32768, ge=1024, le=1048576)
    max_auth_body_bytes: int = Field(4096, ge=256, le=65536)
    log_rejection_interval_s: float = Field(10, ge=1, le=3600)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_redact_patterns: list[str] = []

    @field_validator("mongodb_uri")
    @classmethod
    def _mongo_scheme(cls, v: str) -> str:
        if v and not v.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("must start with mongodb:// or mongodb+srv://")
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_length(cls, v: SecretStr) -> SecretStr:
        if v.get_secret_value() and len(v.get_secret_value()) < 32:
            raise ValueError("must be at least 32 characters")
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_level(cls, v):
        return v.upper() if isinstance(v, str) else v

    @field_validator("log_redact_patterns")
    @classmethod
    def _patterns_compile(cls, v: list[str]) -> list[str]:
        import re
        for i, pattern in enumerate(v):
            try:
                re.compile(pattern)
            except re.error:
                raise ValueError(f"pattern #{i + 1} is not a valid regular expression") from None
        return v

    @model_validator(mode="after")
    def _check_live_requirements(self):
        if self.max_auth_body_bytes > self.max_body_bytes:
            raise ValueError("MAX_AUTH_BODY_BYTES must not exceed MAX_BODY_BYTES")
        known = KNOWN_EMBEDDING_DIMS.get(self.embedding_model)
        if known and self.embedding_dims not in known:
            raise ValueError(f"EMBEDDING_DIMS does not match EMBEDDING_MODEL (expected one of {sorted(known)})")
        if self.app_mode == "live":
            missing = self.missing_credentials + ([] if self.jwt_secret.get_secret_value() else ["JWT_SECRET"])
            if missing:
                raise ValueError("APP_MODE=live requires " + ", ".join(missing))
        return self

    @property
    def missing_credentials(self) -> list[str]:
        required = {"MONGODB_URI": self.mongodb_uri, "OPENAI_API_KEY": self.openai_api_key,
                    "VOYAGE_API_KEY": self.voyage_api_key}
        return [name for name, value in required.items() if not value]

    @property
    def configured(self) -> bool:
        """True when the app runs live (all credentials present and mode is not demo)."""
        return self.app_mode != "demo" and not self.missing_credentials

    @property
    def auth_enabled(self) -> bool:
        """Accounts need a store (MongoDB) and a signing key; demo mode never has them."""
        return self.app_mode != "demo" and bool(self.mongodb_uri) and bool(self.jwt_secret.get_secret_value())

    @property
    def auth_unavailable_reason(self) -> str | None:
        if self.app_mode == "demo":
            return "demo mode has no account store"
        missing = [n for n, v in (("MONGODB_URI", self.mongodb_uri), ("JWT_SECRET", self.jwt_secret.get_secret_value())) if not v]
        return "set " + " and ".join(missing) if missing else None

    @property
    def mode(self) -> str:
        return "live" if self.configured else "demo"


def load_settings(**overrides) -> Settings:
    """Build settings, converting validation failures into a ConfigError without echoing any value."""
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        problems = []
        for err in exc.errors():
            where = ".".join(str(p).upper() for p in err["loc"]) or "settings"
            problems.append(f"{where}: {err['msg'].removeprefix('Value error, ')}")
        raise ConfigError("Invalid configuration: " + "; ".join(problems)) from None


settings = load_settings()
