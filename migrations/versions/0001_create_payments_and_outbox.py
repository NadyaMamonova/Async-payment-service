"""Create payments and outbox tables.

Revision ID: 0001
Revises:
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

currency_enum = postgresql.ENUM(
    "RUB",
    "USD",
    "EUR",
    name="currency",
    create_type=False,
)

payment_status_enum = postgresql.ENUM(
    "pending",
    "succeeded",
    "failed",
    name="payment_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    currency_enum.create(bind, checkfirst=True)
    payment_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", currency_enum, nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            payment_status_enum,
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column(
            "webhook_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "webhook_delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "webhook_attempts >= 0",
            name="ck_payments_webhook_attempts_non_negative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_payments_idempotency_key",
        ),
    )

    op.create_index(
        "ix_payments_status_created_at",
        "payments",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column(
            "aggregate_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "claimed_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_outbox_attempts_non_negative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox"),
    )

    op.create_index(
        "ix_outbox_unpublished_next_attempt",
        "outbox",
        ["next_attempt_at", "claimed_until", "created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index(
        "ix_outbox_unpublished_next_attempt",
        table_name="outbox",
    )
    op.drop_table("outbox")

    op.drop_index(
        "ix_payments_status_created_at",
        table_name="payments",
    )
    op.drop_table("payments")

    payment_status_enum.drop(bind, checkfirst=True)
    currency_enum.drop(bind, checkfirst=True)