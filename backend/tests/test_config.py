import pytest

from app.config import ConfigError, load_settings

SECRET_URI = "mongodb+srv://user:hunter2@cluster.example.net/db"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("APP_MODE", "MONGODB_URI", "OPENAI_API_KEY", "VOYAGE_API_KEY", "EMBEDDING_MODEL",
                 "EMBEDDING_DIMS", "MAX_GRAPH_STEPS", "LOG_LEVEL", "LOG_REDACT_PATTERNS", "JWT_SECRET",
                 "ACCESS_TOKEN_TTL_MINUTES", "RATE_LIMIT_ENABLED"):
        monkeypatch.delenv(name, raising=False)


def load(**kw):
    return load_settings(_env_file=None, **kw)


def full(**kw):
    return load(mongodb_uri=SECRET_URI, openai_api_key="sk-test-123456789", voyage_api_key="pa-test-123456789", **kw)


def test_defaults_run_in_demo_mode_without_credentials():
    s = load()
    assert s.mode == "demo" and not s.configured
    assert s.missing_credentials == ["MONGODB_URI", "OPENAI_API_KEY", "VOYAGE_API_KEY"]


def test_auto_mode_goes_live_when_everything_is_set():
    assert full().mode == "live"


def test_partial_credentials_stay_demo_in_auto_mode():
    s = load(mongodb_uri=SECRET_URI)
    assert s.mode == "demo" and s.missing_credentials == ["OPENAI_API_KEY", "VOYAGE_API_KEY"]


def test_explicit_demo_ignores_credentials():
    assert full(app_mode="demo").mode == "demo"


def test_live_mode_without_credentials_fails_and_names_variables():
    with pytest.raises(ConfigError) as err:
        load(app_mode="live", mongodb_uri=SECRET_URI)
    assert "OPENAI_API_KEY" in str(err.value) and "VOYAGE_API_KEY" in str(err.value)
    assert "hunter2" not in str(err.value)


def test_bad_uri_scheme_is_rejected_without_leaking_it():
    with pytest.raises(ConfigError) as err:
        load(mongodb_uri="postgres://admin:hunter2@host/db")
    assert "MONGODB_URI" in str(err.value) and "hunter2" not in str(err.value)


@pytest.mark.parametrize("field,value", [("max_graph_steps", 1), ("max_graph_steps", 500), ("embedding_dims", 0),
                                         ("mongo_timeout_ms", 10), ("llm_timeout_s", 0), ("app_mode", "prod"),
                                         ("db_name", "bad name!")])
def test_out_of_range_values_are_rejected(field, value):
    with pytest.raises(ConfigError, match=field.upper()):
        load(**{field: value})


def test_embedding_dimensions_must_match_known_model():
    assert load(embedding_model="voyage-3", embedding_dims=1024).embedding_dims == 1024
    with pytest.raises(ConfigError, match="EMBEDDING_DIMS"):
        load(embedding_model="voyage-3", embedding_dims=512)
    assert load(embedding_model="some-future-model", embedding_dims=768).embedding_dims == 768


def test_invalid_redaction_pattern_is_reported_by_position():
    with pytest.raises(ConfigError, match=r"pattern #2"):
        load(log_redact_patterns=["ok", "(unclosed"])


def test_values_come_from_environment(monkeypatch):
    monkeypatch.setenv("MAX_GRAPH_STEPS", "7")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    s = load()
    assert s.max_graph_steps == 7 and s.log_level == "DEBUG"


def test_bad_environment_value_gives_clear_error(monkeypatch):
    monkeypatch.setenv("MAX_GRAPH_STEPS", "lots")
    with pytest.raises(ConfigError, match="MAX_GRAPH_STEPS"):
        load()


KEY = "k" * 40


def test_short_jwt_secret_is_rejected_without_echoing_it():
    with pytest.raises(ConfigError) as err:
        load(jwt_secret="tooshort-secret")
    assert "JWT_SECRET" in str(err.value) and "tooshort-secret" not in str(err.value)


def test_live_mode_requires_a_signing_key():
    with pytest.raises(ConfigError, match="JWT_SECRET"):
        full(app_mode="live")
    assert full(app_mode="live", jwt_secret=KEY).mode == "live"


def test_auth_is_enabled_only_with_a_store_and_a_key_outside_demo():
    assert not load().auth_enabled and not full().auth_enabled
    assert full(jwt_secret=KEY).auth_enabled
    assert not full(jwt_secret=KEY, app_mode="demo").auth_enabled
    assert load(jwt_secret=KEY).auth_unavailable_reason == "set MONGODB_URI"
    assert full().auth_unavailable_reason == "set JWT_SECRET"
    assert full(jwt_secret=KEY, app_mode="demo").auth_unavailable_reason == "demo mode has no account store"


@pytest.mark.parametrize("ttl", [0, 1441])
def test_token_lifetime_is_bounded(ttl):
    with pytest.raises(ConfigError, match="ACCESS_TOKEN_TTL_MINUTES"):
        load(access_token_ttl_minutes=ttl)


def test_signing_key_is_hidden_in_repr():
    assert KEY not in repr(load(jwt_secret=KEY))


def test_abuse_limit_defaults_and_bounds():
    s = load()
    assert (s.rate_register_ip_per_hour, s.rate_login_ip_per_min, s.rate_chat_ip_per_min, s.rate_chat_user_per_min,
            s.rate_read_ip_per_min, s.max_body_bytes, s.max_auth_body_bytes) == (10, 10, 30, 10, 120, 32768, 4096)
    assert s.rate_limit_enabled and s.rate_limit_max_keys == 10000
    for field, bad in [("rate_chat_user_per_min", 0), ("rate_limit_max_keys", 10), ("max_body_bytes", 100),
                       ("max_auth_body_bytes", 10), ("log_rejection_interval_s", 0)]:
        with pytest.raises(ConfigError, match=field.upper()):
            load(**{field: bad})


def test_auth_body_cap_cannot_exceed_the_general_cap():
    with pytest.raises(ConfigError, match="MAX_AUTH_BODY_BYTES"):
        load(max_body_bytes=2048, max_auth_body_bytes=4096)


def test_rate_limits_can_be_disabled_from_the_environment(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    assert load().rate_limit_enabled is False
