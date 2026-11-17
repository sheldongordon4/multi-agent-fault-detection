"""Per-domain settings for the RAG domain — the local embedding model."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class RagConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Local, open-source embedding model. Changing this requires rebuilding the
    # vector DB (dimensionality changes). bge-small-en-v1.5 is 384-dim.
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"


settings = RagConfig()
