"""
Central application settings (pydantic-settings).

Single source of truth for configuration across the API, the Kafka workers, the
detection/coordinator services and the persistence layer. Values are read from the
environment / project-root .env file; everything has a sensible local default so
the app boots for development without a fully-populated .env.
"""

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import Environment


class CustomBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class Config(CustomBaseSettings):
    # ── App ───────────────────────────────────
    APP_ENV: str = Field(default="local")
    ENVIRONMENT: Environment = Environment.LOCAL
    APP_VERSION: str = "0.1"

    # ── Database (Postgres, async) ────────────
    # Async URL is what the app + Alembic actually use; sync is kept for tooling.
    DATABASE_ASYNC_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/mafd"
    )
    DATABASE_URL: str = Field(default="postgresql+psycopg://postgres:postgres@localhost:5432/mafd")
    DATABASE_POOL_SIZE: int = 16
    DATABASE_POOL_TTL: int = 60 * 20  # 20 minutes
    DATABASE_POOL_PRE_PING: bool = True

    # ── Kafka ─────────────────────────────────
    KAFKA_ENABLED: bool = Field(
        default=True,
        description="Start the Kafka consumer workers on app startup.",
    )
    KAFKA_HOST: str = Field(default="localhost")
    KAFKA_PORT: int = Field(default=29092)

    # ── CORS ──────────────────────────────────
    CORS_ORIGINS: list[str] = ["*"]
    CORS_HEADERS: list[str] = ["*"]

    # Domain-specific settings live with their domain (best-practices: one
    # BaseSettings per domain): Azure/LLM -> app/faults/config.py; the embedding
    # model -> app/rag/config.py.

    @property
    def kafka_bootstrap_servers(self) -> str:
        return f"{self.KAFKA_HOST}:{self.KAFKA_PORT}"


settings = Config()

app_configs: dict[str, Any] = {"title": "MAFD API"}
