"""Per-domain settings for the faults (coordinator) domain — LLM + throttling."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class FaultsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Azure OpenAI deployment (used via an OpenAI-compatible base_url).
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4o-mini"

    # Coordinator LLM throttling / reliability.
    LLM_REQUESTS_PER_SECOND: float = 1.0
    LLM_MAX_BUCKET_SIZE: int = 3
    LLM_MAX_RETRIES: int = 2
    LLM_TIMEOUT_SECONDS: float = 60.0

    @property
    def azure_configured(self) -> bool:
        """True only when the Azure deployment is fully + really configured."""
        key = self.AZURE_OPENAI_API_KEY or ""
        endpoint = self.AZURE_OPENAI_ENDPOINT or ""
        return bool(
            key
            and key != "changeme"
            and endpoint
            and "<your-resource>" not in endpoint
            and self.AZURE_OPENAI_DEPLOYMENT
        )


settings = FaultsConfig()
