from dataclasses import dataclass

from app.db.models.payment import Payment


@dataclass(frozen=True, slots=True)
class PaymentCreationResult:
    """Result of a new or idempotently repeated payment request."""

    payment: Payment
    created: bool