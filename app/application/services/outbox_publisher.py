import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import Random, SystemRandom
from uuid import UUID, uuid4

from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models.outbox import OutboxEvent
from app.db.repositories.outbox import OutboxRepository
from app.messaging.constants import (
    ORIGINAL_EVENT_ID_HEADER,
    PAYMENTS_NEW_ROUTING_KEY,
    PROCESSING_ATTEMPT_HEADER,
)
from app.messaging.topology import payments_exchange

logger = logging.getLogger(__name__)

MAX_STORED_ERROR_LENGTH = 2000


@dataclass(frozen=True, slots=True)
class OutboxBatchResult:
    claimed: int
    published: int
    failed: int


class OutboxPublisher:
    """Publish transactionally stored events with at-least-once delivery."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        broker: RabbitBroker,
        settings: Settings,
        random_source: Random | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker
        self._settings = settings
        self._random = random_source or SystemRandom()
        self._publish_semaphore = asyncio.Semaphore(
            settings.outbox_publish_concurrency
        )

    async def publish_pending_batch(self) -> OutboxBatchResult:
        claim_id = uuid4()
        current_time = datetime.now(UTC)
        claimed_until = current_time + timedelta(
            seconds=self._settings.outbox_claim_ttl_seconds
        )

        async with self._session_factory() as session, session.begin():
            repository = OutboxRepository(session)
            events = await repository.claim_pending_batch(
                current_time=current_time,
                claimed_until=claimed_until,
                claim_id=claim_id,
                batch_size=self._settings.outbox_batch_size,
            )

        if not events:
            return OutboxBatchResult(
                claimed=0,
                published=0,
                failed=0,
            )

        results = await asyncio.gather(
            *(
                self._publish_one(
                    event=event,
                    claim_id=claim_id,
                )
                for event in events
            )
        )

        published_count = sum(results)
        return OutboxBatchResult(
            claimed=len(events),
            published=published_count,
            failed=len(events) - published_count,
        )

    async def _publish_one(
        self,
        *,
        event: OutboxEvent,
        claim_id: UUID,
    ) -> bool:
        async with self._publish_semaphore:
            try:
                confirmation = await self._broker.publish(
                    event.payload,
                    exchange=payments_exchange,
                    routing_key=PAYMENTS_NEW_ROUTING_KEY,
                    mandatory=True,
                    persist=True,
                    timeout=(
                        self._settings
                        .rabbitmq_publish_timeout_seconds
                    ),
                    message_id=str(event.id),
                    correlation_id=str(event.aggregate_id),
                    message_type=event.event_type,
                    timestamp=event.created_at,
                    headers={
                        ORIGINAL_EVENT_ID_HEADER: str(event.id),
                        PROCESSING_ATTEMPT_HEADER: 1,
                    },
                )

                if confirmation is None:
                    raise RuntimeError(
                        "RabbitMQ did not return a publisher confirmation"
                    )
            except Exception as error:
                await self._record_failure(
                    event=event,
                    claim_id=claim_id,
                    error=error,
                )
                return False

            await self._record_success(
                event=event,
                claim_id=claim_id,
            )
            return True

    async def _record_success(
        self,
        *,
        event: OutboxEvent,
        claim_id: UUID,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            repository = OutboxRepository(session)
            updated = await repository.mark_published(
                event_id=event.id,
                claim_id=claim_id,
                published_at=datetime.now(UTC),
            )

        if not updated:
            logger.warning(
                "Outbox claim was lost after successful publication",
                extra={
                    "event_id": str(event.id),
                    "payment_id": str(event.aggregate_id),
                },
            )
            return

        logger.info(
            "Outbox event published",
            extra={
                "event_id": str(event.id),
                "payment_id": str(event.aggregate_id),
                "event_type": event.event_type,
            },
        )

    async def _record_failure(
        self,
        *,
        event: OutboxEvent,
        claim_id: UUID,
        error: Exception,
    ) -> None:
        failure_number = event.attempts + 1
        retry_delay = self._calculate_retry_delay(failure_number)
        next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=retry_delay
        )
        error_message = (
            f"{type(error).__name__}: {error}"
        )[:MAX_STORED_ERROR_LENGTH]

        async with self._session_factory() as session, session.begin():
            repository = OutboxRepository(session)
            updated = await repository.mark_failed(
                event_id=event.id,
                claim_id=claim_id,
                next_attempt_at=next_attempt_at,
                error_message=error_message,
            )

        logger.error(
            "Outbox publication failed",
            extra={
                "event_id": str(event.id),
                "payment_id": str(event.aggregate_id),
                "failure_number": failure_number,
                "retry_delay_seconds": retry_delay,
                "claim_was_current": updated,
                "error_type": type(error).__name__,
            },
        )

    def _calculate_retry_delay(self, failure_number: int) -> float:
        exponent = min(failure_number - 1, 20)
        exponential_delay = min(
            self._settings.retry_base_delay_seconds
            * (2**exponent),
            self._settings.outbox_max_retry_delay_seconds,
        )

        jitter_multiplier = float(
            self._random.uniform(
                1 - self._settings.retry_jitter_ratio,
                1 + self._settings.retry_jitter_ratio,
            )
        )

        return float(
            max(
                0.001,
                exponential_delay * jitter_multiplier,
            )
        )