from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Currency, PaymentStatus
from app.db.base import Base


class Payment(Base):
    """Persistent representation of a payment."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("webhook_attempts >= 0", name="webhook_attempts_non_negative"),
        Index("ix_payments_status_created_at", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    currency: Mapped[Currency] = mapped_column(
        Enum(
            Currency,
            name="currency",
            values_callable=lambda enum_class: [
                enum_member.value for enum_member in enum_class
            ],
        ),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(length=500),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(
            PaymentStatus,
            name="payment_status",
            values_callable=lambda enum_class: [
                enum_member.value for enum_member in enum_class
            ],
        ),
        nullable=False,
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(length=255),
        nullable=False,
        unique=True,
    )
    request_fingerprint: Mapped[str] = mapped_column(
        String(length=64),
        nullable=False,
    )
    webhook_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    webhook_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    webhook_delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )