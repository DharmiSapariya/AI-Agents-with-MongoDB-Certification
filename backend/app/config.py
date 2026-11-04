"""Environment-based configuration. No secrets are ever hardcoded or persisted."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mongodb_uri: str = ""
    openai_api_key: str = ""
    voyage_api_key: str = ""
    db_name: str = "ai_agents"
    checkpoint_db: str = "checkpointing_db"
    llm_model: str = "gpt-4o"
    embedding_model: str = "voyage-3-lite"
    embedding_dims: int = 512
    vector_index: str = "vector_index"
    max_graph_steps: int = 12
    mongo_timeout_ms: int = 5000

    @property
    def configured(self) -> bool:
        return bool(self.mongodb_uri and self.openai_api_key and self.voyage_api_key)


settings = Settings()
