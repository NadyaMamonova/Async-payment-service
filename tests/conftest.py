from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.core.config import Settings
from app.core.enums import Currency, PaymentStatus
from app.db.models.payment import Payment
from app.schemas.payment import PaymentCreateRequest


@pytest.fixture
def settings() -> Settings:
    """Return isolated settings suitable for unit tests."""

    return Settings(
        api_key="unit-test-api-key",
        database_url=(
            "postgresql+asyncpg://payments:payments@localhost/payments"
        ),
        rabbitmq_url="amqp://guest:guest@localhost/",
        webhook_signing_secret=(
            "unit-test-webhook-signing-secret-at-least-32-characters"
        ),
        webhook_allowed_private_hosts=frozenset({"mock-webhook"}),
        payment_processing_min_delay_seconds=0,
        payment_processing_max_delay_seconds=0,
    )


@pytest.fixture
def payment_request() -> PaymentCreateRequest:
    return PaymentCreateRequest(
        amount="100.50",
        currency="RUB",
        description="Тестовый платёж",
        metadata={
            "order_id": "order-42",
            "customer_id": "customer-17",
        },
        webhook_url="http://mock-webhook:8001/webhook",
    )


@pytest.fixture
def processed_payment() -> Payment:
    current_time = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)

    return Payment(
        id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Тестовый платёж",
        metadata_={"order_id": "order-42"},
        status=PaymentStatus.SUCCEEDED,
        idempotency_key="unit-test-idempotency-key",
        request_fingerprint="a" * 64,
        webhook_url="http://mock-webhook:8001/webhook",
        webhook_attempts=0,
        created_at=current_time,
        updated_at=current_time,
        processed_at=current_time,
    )