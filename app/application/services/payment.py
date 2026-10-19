from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.idempotency import (
    calculate_payment_request_fingerprint,
)
from app.application.results import PaymentCreationResult
from app.core.enums import EventType, PaymentStatus
from app.core.exceptions import (
    IdempotencyConflictError,
    PaymentNotFoundError,
)
from app.db.models.outbox import OutboxEvent
from app.db.models.payment import Payment
from app.db.repositories.outbox import OutboxRepository
from app.db.repositories.payment import PaymentRepository
from app.schemas.events import PaymentCreatedEvent
from app.schemas.payment import PaymentCreateRequest


class PaymentService:
    """Coordinate payment use cases and their transaction boundaries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._payments = PaymentRepository(session)
        self._outbox = OutboxRepository(session)

    async def create_payment(
        self,
        *,
        request: PaymentCreateRequest,
        idempotency_key: str,
    ) -> PaymentCreationResult:
        fingerprint = calculate_payment_request_fingerprint(request)

        try:
            async with self._session.begin():
                existing_payment = (
                    await self._payments.get_by_idempotency_key(
                        idempotency_key
                    )
                )
                if existing_payment is not None:
                    return self._resolve_existing_payment(
                        existing_payment,
                        fingerprint,
                    )

                payment = await self._create_payment_and_event(
                    request=request,
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                )

                return PaymentCreationResult(
                    payment=payment,
                    created=True,
                )
        except IntegrityError as error:
            return await self._resolve_concurrent_idempotency_request(
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                original_error=error,
            )

    async def get_payment(self, payment_id: UUID) -> Payment:
        payment = await self._payments.get_by_id(payment_id)
        if payment is None:
            raise PaymentNotFoundError()
        return payment

    async def _create_payment_and_event(
        self,
        *,
        request: PaymentCreateRequest,
        idempotency_key: str,
        fingerprint: str,
    ) -> Payment:
        payment_id = uuid4()
        event_id = uuid4()
        current_time = datetime.now(UTC)

        payment = Payment(
            id=payment_id,
            amount=request.amount,
            currency=request.currency,
            description=request.description,
            metadata_=request.metadata,
            status=PaymentStatus.PENDING,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            webhook_url=str(request.webhook_url),
            webhook_attempts=0,
            created_at=current_time,
            updated_at=current_time,
        )
        await self._payments.add(payment)

        integration_event = PaymentCreatedEvent(
            event_id=event_id,
            occurred_at=current_time,
            payment_id=payment_id,
        )

        outbox_event = OutboxEvent(
            id=event_id,
            aggregate_type="payment",
            aggregate_id=payment_id,
            event_type=EventType.PAYMENT_CREATED.value,
            payload=integration_event.model_dump(mode="json"),
            attempts=0,
            created_at=current_time,
            next_attempt_at=current_time,
        )
        await self._outbox.add(outbox_event)

        return payment

    async def _resolve_concurrent_idempotency_request(
        self,
        *,
        idempotency_key: str,
        fingerprint: str,
        original_error: IntegrityError,
    ) -> PaymentCreationResult:
        async with self._session.begin():
            existing_payment = (
                await self._payments.get_by_idempotency_key(
                    idempotency_key
                )
            )

            if existing_payment is None:
                raise original_error

            return self._resolve_existing_payment(
                existing_payment,
                fingerprint,
            )

    @staticmethod
    def _resolve_existing_payment(
        payment: Payment,
        fingerprint: str,
    ) -> PaymentCreationResult:
        if payment.request_fingerprint != fingerprint:
            raise IdempotencyConflictError()

        return PaymentCreationResult(
            payment=payment,
            created=False,
        )