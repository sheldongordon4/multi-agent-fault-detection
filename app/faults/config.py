"""Per-domain settings for the faults (coordinator) domain — LLM + throttling."""

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Hard, code-level ceilings on the cost knobs. These are NOT configurable: every
# .env / env-var value below is clamped into these ranges, so a typo or an
# over-eager override can never raise spend past what the code allows. Lower the
# effective limits via .env; you cannot raise them past these.
HARD_MAX_RETRIES = 3
HARD_MAX_OUTPUT_TOKENS = 2048
# Sized for the Table 4 latency run: 50 sampled events + 1 discarded warm-up, at
# ~2 endpoint calls per diagnosis = 102, plus headroom for the occasional second
# retrieval round. The number is a spend cap enforced before any network I/O —
# on a metered provider it bounds the bill, on a free tier it bounds how fast
# you can burn the daily quota.
HARD_MAX_ENDPOINT_CALLS = 150

# Google AI Studio's OpenAI-compatible surface — the default endpoint. A default,
# not a hard-coded provider; see the note on LLM_ENDPOINT below.
GOOGLE_AI_STUDIO_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class FaultsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── The coordinator's chat model ────────────────────────────────────────
    #
    # Deliberately provider-NEUTRAL. `app/faults/agent.py` builds a plain
    # `ChatOpenAI` pointed at `base_url`, never a provider-specific client, so
    # any endpoint speaking the OpenAI chat-completions protocol works with no
    # code change: Google AI Studio (the default), Azure OpenAI / AI Foundry,
    # Groq, OpenRouter, Together — or a self-hosted vLLM / Ollama, which is what
    # docs/System_Architecture.md §9 wants in production, since grid data must
    # not leave the premises.
    #
    # That portability is why moving off Azure was a config change: switching
    # providers means a different base_url, key and model id, nothing more.
    #
    # The AZURE_OPENAI_* names are kept as ALIASES so an existing .env keeps
    # working. They are the old names for these same three values, not a second
    # provider — there is only ever one endpoint configured.
    LLM_ENDPOINT: str | None = Field(
        default=GOOGLE_AI_STUDIO_BASE_URL,
        validation_alias=AliasChoices("LLM_ENDPOINT", "AZURE_OPENAI_ENDPOINT"),
    )
    LLM_API_KEY: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "AZURE_OPENAI_API_KEY"),
    )
    LLM_MODEL: str = Field(
        default="gemini-3.8-flash",
        validation_alias=AliasChoices("LLM_MODEL", "AZURE_OPENAI_DEPLOYMENT"),
    )

    # Which client class the agent builds. "auto" picks `google` when the
    # endpoint is Google's, `openai` otherwise.
    #
    # WHY THIS EXISTS — Google needs its own client, not the OpenAI-compatible
    # one. Gemini 3.x attaches a `thought_signature` to every function call and
    # requires it echoed back when the tool result is returned. The
    # OpenAI-compatibility layer has nowhere to carry that field, so a
    # SINGLE-turn call succeeds and a multi-turn TOOL LOOP fails on the second
    # request with:
    #
    #   400 INVALID_ARGUMENT — Function call is missing a thought_signature in
    #   functionCall parts ... position 2
    #
    # The coordinator is a ReAct loop, so it is always multi-turn. Gemini 2.x
    # predates the requirement but is closed to new API projects, so there is no
    # version to fall back to. Every other provider stays on `ChatOpenAI`.
    LLM_PROVIDER: str = "auto"

    # Coordinator LLM throttling / reliability.
    LLM_REQUESTS_PER_SECOND: float = 1.0
    LLM_MAX_BUCKET_SIZE: int = 3
    LLM_MAX_RETRIES: int = 1
    LLM_TIMEOUT_SECONDS: float = 60.0

    # Cost guardrails (configurable via .env, but clamped to the HARD_* ceilings
    # above). LLM_MAX_OUTPUT_TOKENS caps tokens billed per completion;
    # LLM_MAX_ENDPOINT_CALLS is the total number of chat calls this process may
    # make before the coordinator stops and permanently uses the local (no-LLM)
    # fallback — a hard budget so a runaway loop or a long-lived worker can't
    # drain a paid credit or exhaust a free tier's daily quota.
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
    def resolved_provider(self) -> str:
        """`LLM_PROVIDER`, with "auto" resolved from the endpoint host."""
        choice = (self.LLM_PROVIDER or "auto").strip().lower()
        if choice in {"google", "openai"}:
            return choice
        return "google" if "generativelanguage.googleapis.com" in (self.LLM_ENDPOINT or "") else "openai"

    @property
    def llm_configured(self) -> bool:
        """
        True only when the endpoint is fully AND really configured.

        "Really" is the load-bearing word: a key still reading `changeme`, or an
        endpoint still carrying a `<placeholder>`, counts as unconfigured, so a
        half-filled .env takes the offline heuristic path instead of failing at
        the first fault event. The endpoint carries a working default, so in
        practice this turns on the moment a real API key is present.
        """
        key = self.LLM_API_KEY.get_secret_value() if self.LLM_API_KEY else ""
        endpoint = self.LLM_ENDPOINT or ""
        placeholder = key.lower() in {"changeme", "none", "your-key", "<your-key>"}
        return bool(
            key and not placeholder and endpoint and "<" not in endpoint and self.LLM_MODEL
        )

    # Kept so an older import path or a stale call site fails loudly at the name
    # rather than silently reading a missing attribute as falsy.
    @property
    def azure_configured(self) -> bool:  # pragma: no cover - compatibility shim
        raise AttributeError("azure_configured was renamed to llm_configured")


settings = FaultsConfig()
