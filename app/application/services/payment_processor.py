from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.services.payment_gateway import PaymentGateway
from app.application.services.webhook import WebhookSender
from app.core.enums import PaymentStatus
from app.core.exceptions import (
    PermanentProcessingError,
    PermanentWebhookError,
    RetryableWebhookError,
)
from app.db.models.payment import Payment
from app.db.repositories.payment import PaymentRepository
from app.schemas.events import PaymentCreatedEvent

MAX_ERROR_MESSAGE_LENGTH: Final = 2_000


class PaymentProcessor:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        payment_gateway: PaymentGateway,
        webhook_sender: WebhookSender,
    ) -> None:
        self._session_factory = session_factory
        self._payment_gateway = payment_gateway
        self._webhook_sender = webhook_sender

    async def process(self, event: PaymentCreatedEvent) -> None:
        payment = await self._get_payment(event.payment_id)

        if payment.status is PaymentStatus.PENDING:
            resulting_status = await self._payment_gateway.process_payment(
                payment_id=payment.id,
                amount=format(payment.amount, ".2f"),
                currency=payment.currency,
            )
            payment = await self._finalize_payment(
                payment_id=payment.id,
                resulting_status=resulting_status,
            )

        if payment.webhook_delivered_at is not None:
            return

        if payment.processed_at is None:
            raise PermanentProcessingError(
                "Finalized payment does not have processed_at"
            )

        try:
            await self._webhook_sender.send_payment_processed(payment)
        except (RetryableWebhookError, PermanentWebhookError) as error:
            await self._record_webhook_failure(
                payment_id=payment.id,
                error=error,
            )
            raise

        await self._record_webhook_success(payment.id)

    async def _get_payment(self, payment_id: UUID) -> Payment:
        async with self._session_factory() as session:
            repository = PaymentRepository(session)
            payment = await repository.get_by_id(payment_id)

        if payment is None:
            raise PermanentProcessingError(
                f"Payment {payment_id} was not found"
            )

        return payment

    async def _finalize_payment(
        self,
        *,
        payment_id: UUID,
        resulting_status: PaymentStatus,
    ) -> Payment:
        async with self._session_factory.begin() as session:
            repository = PaymentRepository(session)
            payment = await repository.get_for_processing(payment_id)

            if payment is None:
                raise PermanentProcessingError(
                    f"Payment {payment_id} was not found"
                )

            if payment.status is PaymentStatus.PENDING:
                current_time = datetime.now(UTC)
                payment.status = resulting_status
                payment.processed_at = current_time
                payment.updated_at = current_time
                payment.last_error = None

            return payment

    async def _record_webhook_success(self, payment_id: UUID) -> None:
        async with self._session_factory.begin() as session:
            repository = PaymentRepository(session)
            payment = await repository.get_for_processing(payment_id)

            if payment is None:
                raise PermanentProcessingError(
                    f"Payment {payment_id} was not found"
                )

            if payment.webhook_delivered_at is not None:
                return

            current_time = datetime.now(UTC)
            payment.webhook_attempts += 1
            payment.webhook_delivered_at = current_time
            payment.updated_at = current_time
            payment.last_error = None

    async def _record_webhook_failure(
        self,
        *,
        payment_id: UUID,
        error: Exception,
    ) -> None:
        async with self._session_factory.begin() as session:
            repository = PaymentRepository(session)
            payment = await repository.get_for_processing(payment_id)

            if payment is None:
                raise PermanentProcessingError(
                    f"Payment {payment_id} was not found"
                )

            payment.webhook_attempts += 1
            payment.updated_at = datetime.now(UTC)
            payment.last_error = str(error)[:MAX_ERROR_MESSAGE_LENGTH]