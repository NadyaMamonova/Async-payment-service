from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MockWebhookSettings(BaseSettings):
    """Configuration of the local webhook receiver."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    webhook_signing_secret: SecretStr = Field(min_length=32)

    mock_webhook_failures_before_success: int = Field(
        default=0,
        ge=0,
        le=100,
    )
    mock_webhook_failure_status: int = Field(
        default=503,
        ge=400,
        le=599,
    )
    mock_webhook_success_status: int = Field(
        default=204,
        ge=200,
        le=299,
    )
    mock_webhook_timestamp_tolerance_seconds: int = Field(
        default=300,
        ge=1,
        le=3600,
    )


@lru_cache
def get_mock_webhook_settings() -> MockWebhookSettings:
    return MockWebhookSettings()