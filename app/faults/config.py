"""Per-domain settings for the faults (coordinator) domain — LLM + throttling."""

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Hard, code-level ceilings on the cost knobs. These are NOT configurable: every
# .env / env-var value below is clamped into these ranges, so a typo or an
# over-eager override can never raise spend past what the code allows. Lower the
# effective limits via .env; you cannot raise them past these.
HARD_MAX_RETRIES = 3
HARD_MAX_OUTPUT_TOKENS = 2048
HARD_MAX_ENDPOINT_CALLS = 2


class FaultsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Azure OpenAI deployment (used via an OpenAI-compatible base_url).
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: SecretStr | None = None
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-5.4-mini"

    # Coordinator LLM throttling / reliability.
    LLM_REQUESTS_PER_SECOND: float = 1.0
    LLM_MAX_BUCKET_SIZE: int = 3
    LLM_MAX_RETRIES: int = 1
    LLM_TIMEOUT_SECONDS: float = 60.0

    # Cost guardrails (configurable via .env, but clamped to the HARD_* ceilings
    # above). LLM_MAX_OUTPUT_TOKENS caps tokens billed per completion;
    # LLM_MAX_ENDPOINT_CALLS is the total number of Azure chat calls this process
    # may make before the coordinator stops and permanently uses the local
    # (no-LLM) fallback — a hard budget so a runaway loop or a long-lived worker
    # can't drain your Azure credit.
    LLM_MAX_OUTPUT_TOKENS: int = 1000
    LLM_MAX_ENDPOINT_CALLS: int = 2

    @field_validator("LLM_MAX_RETRIES")
    @classmethod
    def _clamp_retries(cls, v: int) -> int:
        return max(0, min(v, HARD_MAX_RETRIES))

    @field_validator("LLM_MAX_OUTPUT_TOKENS")
    @classmethod
    def _clamp_output_tokens(cls, v: int) -> int:
        return max(1, min(v, HARD_MAX_OUTPUT_TOKENS))

    @field_validator("LLM_MAX_ENDPOINT_CALLS")
    @classmethod
    def _clamp_endpoint_calls(cls, v: int) -> int:
        return max(0, min(v, HARD_MAX_ENDPOINT_CALLS))

    @property
    def azure_configured(self) -> bool:
        """True only when the Azure deployment is fully + really configured."""
        key = self.AZURE_OPENAI_API_KEY.get_secret_value() if self.AZURE_OPENAI_API_KEY else ""
        endpoint = self.AZURE_OPENAI_ENDPOINT or ""
        return bool(
            key
            and key != "changeme"
            and endpoint
            and "<your-resource>" not in endpoint
            and self.AZURE_OPENAI_DEPLOYMENT
        )


settings = FaultsConfig()
