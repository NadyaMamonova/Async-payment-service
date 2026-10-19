from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.payment import PaymentCreateRequest


@pytest.mark.parametrize(
    ("raw_amount", "expected_amount"),
    [
        (100, Decimal("100.00")),
        (100.5, Decimal("100.50")),
        ("100", Decimal("100.00")),
        ("100.50", Decimal("100.50")),
        (Decimal("100.50"), Decimal("100.50")),
    ],
)
def test_payment_amount_is_normalized(
    raw_amount: Any,
    expected_amount: Decimal,
) -> None:
    request = PaymentCreateRequest(
        amount=raw_amount,
        currency="RUB",
        description="Заказ 42",
        webhook_url="https://example.com/webhook",
    )

    assert request.amount == expected_amount
    assert request.model_dump(mode="json")["amount"] == format(
        expected_amount,
        ".2f",
    )


@pytest.mark.parametrize(
    "raw_amount",
    [
        True,
        0,
        -1,
        "10.001",
        "NaN",
        "Infinity",
        "not-a-number",
    ],
)
def test_invalid_payment_amount_is_rejected(
    raw_amount: Any,
) -> None:
    with pytest.raises(ValidationError):
        PaymentCreateRequest(
            amount=raw_amount,
            currency="RUB",
            description="Заказ 42",
            webhook_url="https://example.com/webhook",
        )


def test_unknown_request_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        PaymentCreateRequest.model_validate(
            {
                "amount": "100.00",
                "currency": "RUB",
                "description": "Заказ 42",
                "webhook_url": "https://example.com/webhook",
                "unexpected_field": "unexpected-value",
            }
        )


def test_unsupported_currency_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PaymentCreateRequest(
            amount="100.00",
            currency="GBP",
            description="Заказ 42",
            webhook_url="https://example.com/webhook",
        )