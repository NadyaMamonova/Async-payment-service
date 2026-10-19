from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Self
from uuid import UUID

import orjson
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import Currency, PaymentStatus
from app.db.models.payment import Payment

AMOUNT_QUANTUM = Decimal("0.01")
MAX_PAYMENT_AMOUNT = Decimal("9999999999999999.99")
MAX_METADATA_SIZE_BYTES = 16 * 1024


class PaymentCreateRequest(BaseModel):
    """Validated input for creating a payment."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    amount: Decimal
    currency: Currency
    description: str = Field(min_length=1, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: AnyHttpUrl

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: object) -> Decimal:
        if isinstance(value, bool):
            raise ValueError("Amount must be a decimal number")

        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise ValueError("Amount must be a decimal number") from error

        if not amount.is_finite():
            raise ValueError("Amount must be finite")

        if amount <= 0:
            raise ValueError("Amount must be greater than zero")

        if amount > MAX_PAYMENT_AMOUNT:
            raise ValueError(
                f"Amount must not exceed {MAX_PAYMENT_AMOUNT}"
            )

        exponent = amount.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -2:
            raise ValueError(
                "Amount must contain no more than two decimal places"
            )

        return amount.quantize(AMOUNT_QUANTUM)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        if not value:
            raise ValueError("Description must not be empty")
        return value

    @model_validator(mode="after")
    def validate_metadata(self) -> Self:
        try:
            serialized_metadata = orjson.dumps(
                self.metadata,
                option=orjson.OPT_SORT_KEYS,
            )
        except TypeError as error:
            raise ValueError(
                "Metadata must contain only valid JSON values"
            ) from error

        if len(serialized_metadata) > MAX_METADATA_SIZE_BYTES:
            raise ValueError(
                f"Metadata must not exceed {MAX_METADATA_SIZE_BYTES} bytes"
            )

        return self


class PaymentAcceptedResponse(BaseModel):
    """Short response returned after asynchronous payment acceptance."""

    payment_id: UUID
    status: PaymentStatus
    created_at: datetime

    @classmethod
    def from_payment(cls, payment: Payment) -> Self:
        return cls(
            payment_id=payment.id,
            status=payment.status,
            created_at=payment.created_at,
        )


class PaymentDetailResponse(BaseModel):
    """Complete public representation of a payment."""

    payment_id: UUID
    amount: str
    currency: Currency
    description: str
    metadata: dict[str, Any]
    status: PaymentStatus
    webhook_url: str
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None
    webhook_delivered_at: datetime | None

    @classmethod
    def from_payment(cls, payment: Payment) -> Self:
        return cls(
            payment_id=payment.id,
            amount=format(payment.amount, ".2f"),
            currency=payment.currency,
            description=payment.description,
            metadata=payment.metadata_,
            status=payment.status,
            webhook_url=payment.webhook_url,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
            processed_at=payment.processed_at,
            webhook_delivered_at=payment.webhook_delivered_at,
        )