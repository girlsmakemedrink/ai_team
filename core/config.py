"""Application settings, loaded from environment via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # === Auth (ADR-005) ===
    owner_token: SecretStr = Field(default=SecretStr("dev-token-replace-me-min-32-chars-aaaa"),
                                    min_length=32)
    hmac_secret: SecretStr = Field(default=SecretStr("dev-hmac-replace-me-min-32-chars-bbbbb"),
                                    min_length=32)

    # === LLM (ADR-006, ADR-008) ===
    llm_model_haiku: str = "claude-haiku-4-5"
    llm_model_sonnet: str = "claude-sonnet-4-6"
    llm_model_opus: str = "claude-opus-4-7"
    llm_monthly_quota_tokens: int = 10_000_000
    llm_quota_soft_warn_pct: int = 70
    llm_quota_pause_pct: int = 90

    # === Postgres ===
    postgres_dsn: str = (
        "postgresql+asyncpg://ai_team:changeme-local-only@localhost:5432/ai_team"
    )

    # === Redis ===
    redis_url: str = "redis://localhost:6379/0"

    # === API ===
    api_host: str = "0.0.0.0"  # noqa: S104  bind any iface for local docker
    api_port: int = 8000

    # === Observability ===
    log_level: str = "INFO"
    prometheus_port: int = 9090

    # === Target repo defaults (ADR-009) ===
    default_target_repo: str = "."
    default_target_repo_branch: str = "develop"

    # === Checkpoint (ADR-007) ===
    checkpoint_interval_min: int = 30


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
