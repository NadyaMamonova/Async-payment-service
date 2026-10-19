from datetime import datetime
from typing import Any, Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict

from app.core.enums import Currency, PaymentStatus, WebhookEventType
from app.db.models.payment import Payment


class PaymentProcessedWebhook(BaseModel):
    """Versioned webhook sent after payment processing."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event: WebhookEventType = WebhookEventType.PAYMENT_PROCESSED
    event_version: Literal[1] = 1
    payment_id: UUID
    status: PaymentStatus
    amount: str
    currency: Currency
    processed_at: datetime
    metadata: dict[str, Any]

    @classmethod
    def from_payment(cls, payment: Payment) -> Self:
        if payment.processed_at is None:
            raise ValueError(
                "Cannot build a webhook for an unprocessed payment"
            )

        event_id = uuid5(
            NAMESPACE_URL,
            (
                f"payment:{payment.id}:"
                f"{WebhookEventType.PAYMENT_PROCESSED.value}:"
                f"{payment.status.value}"
            ),
        )

        return cls(
            event_id=event_id,
            payment_id=payment.id,
            status=payment.status,
            amount=format(payment.amount, ".2f"),
            currency=payment.currency,
            processed_at=payment.processed_at,
            metadata=payment.metadata_,
        )