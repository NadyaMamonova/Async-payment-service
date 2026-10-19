from app.application.idempotency import (
    calculate_payment_request_fingerprint,
)
from app.schemas.payment import PaymentCreateRequest


def test_equivalent_requests_have_same_fingerprint() -> None:
    first_request = PaymentCreateRequest(
        amount=100,
        currency="RUB",
        description="Заказ 42",
        metadata={"order_id": "42", "customer_id": "17"},
        webhook_url="https://example.com/webhook",
    )
    second_request = PaymentCreateRequest(
        amount="100.00",
        currency="RUB",
        description="Заказ 42",
        metadata={"customer_id": "17", "order_id": "42"},
        webhook_url="https://example.com/webhook",
    )

    assert calculate_payment_request_fingerprint(
        first_request
    ) == calculate_payment_request_fingerprint(second_request)


def test_different_requests_have_different_fingerprints() -> None:
    first_request = PaymentCreateRequest(
        amount="100.00",
        currency="RUB",
        description="Заказ 42",
        webhook_url="https://example.com/webhook",
    )
    second_request = PaymentCreateRequest(
        amount="101.00",
        currency="RUB",
        description="Заказ 42",
        webhook_url="https://example.com/webhook",
    )

    assert calculate_payment_request_fingerprint(
        first_request
    ) != calculate_payment_request_fingerprint(second_request)