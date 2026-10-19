from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Async Payment Processing Service"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    api_key: SecretStr = Field(min_length=16)

    database_url: str
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)

    rabbitmq_url: str

    payment_processing_min_delay_seconds: float = Field(default=2.0, ge=0)
    payment_processing_max_delay_seconds: float = Field(default=5.0, ge=0)
    payment_success_rate: float = Field(default=0.9, ge=0, le=1)

    processing_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_delay_seconds: float = Field(default=1.0, gt=0)
    retry_jitter_ratio: float = Field(default=0.2, ge=0, le=0.5)

    outbox_batch_size: int = Field(default=100, ge=1, le=1000)
    outbox_poll_interval_seconds: float = Field(default=0.5, gt=0)
    outbox_claim_ttl_seconds: float = Field(default=120.0, gt=0)
    outbox_publish_concurrency: int = Field(default=10, ge=1, le=100)
    outbox_max_retry_delay_seconds: float = Field(
        default=60.0,
        gt=0,
    )
    rabbitmq_publish_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=60,
    )

    webhook_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    webhook_signing_secret: SecretStr = Field(min_length=32)
    webhook_require_https: bool = True
    webhook_allowed_private_hosts: frozenset[str] = frozenset({"mock-webhook"})

    @model_validator(mode="after")
    def validate_payment_processing_delay(self) -> Self:
        if (
            self.payment_processing_min_delay_seconds
            > self.payment_processing_max_delay_seconds
        ):
            raise ValueError(
                "PAYMENT_PROCESSING_MIN_DELAY_SECONDS must not exceed "
                "PAYMENT_PROCESSING_MAX_DELAY_SECONDS"
            )
        if self.outbox_publish_concurrency > self.outbox_batch_size:
            raise ValueError(
                "OUTBOX_PUBLISH_CONCURRENCY must not exceed "
                "OUTBOX_BATCH_SIZE"
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide immutable configuration instance."""

    return Settings()