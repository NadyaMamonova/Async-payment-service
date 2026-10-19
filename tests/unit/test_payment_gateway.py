from uuid import UUID

import pytest

from app.application.services.payment_gateway import (
    PaymentGatewayEmulator,
)
from app.core.config import Settings
from app.core.enums import Currency, PaymentStatus


@pytest.mark.asyncio
async def test_gateway_result_is_deterministic(
    settings: Settings,
) -> None:
    gateway = PaymentGatewayEmulator(settings)
    payment_id = UUID("550e8400-e29b-41d4-a716-446655440000")

    first_result = await gateway.process_payment(
        payment_id=payment_id,
        amount="100.00",
        currency=Currency.RUB,
    )
    second_result = await gateway.process_payment(
        payment_id=payment_id,
        amount="100.00",
        currency=Currency.RUB,
    )

    assert first_result is second_result


@pytest.mark.asyncio
async def test_gateway_can_be_configured_for_success(
    settings: Settings,
) -> None:
    successful_settings = settings.model_copy(
        update={"payment_success_rate": 1.0}
    )
    gateway = PaymentGatewayEmulator(successful_settings)

    result = await gateway.process_payment(
        payment_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        amount="100.00",
        currency=Currency.RUB,
    )

    assert result is PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_gateway_can_be_configured_for_failure(
    settings: Settings,
) -> None:
    failed_settings = settings.model_copy(
        update={"payment_success_rate": 0.0}
    )
    gateway = PaymentGatewayEmulator(failed_settings)

    result = await gateway.process_payment(
        payment_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        amount="100.00",
        currency=Currency.RUB,
    )

    assert result is PaymentStatus.FAILED