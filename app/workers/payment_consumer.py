import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from faststream import AckPolicy
from faststream.rabbit import RabbitMessage
from pydantic import ValidationError

from app.application.services.payment_gateway import PaymentGatewayEmulator
from app.application.services.payment_processor import PaymentProcessor
from app.application.services.webhook import WebhookSender
from app.core.config import get_settings
from app.core.exceptions import (
    PermanentProcessingError,
    RetryableProcessingError,
)
from app.core.logging import configure_logging
from app.db.session import (
    async_session_factory,
    dispose_database_engine,
)
from app.messaging.broker import broker, declare_broker_topology
from app.messaging.constants import (
    ORIGINAL_EVENT_ID_HEADER,
    PROCESSING_ATTEMPT_HEADER,
)
from app.messaging.topology import (
    payments_exchange,
    payments_queue,
    select_retry_bucket,
)
from app.schemas.events import PaymentCreatedEvent

logger = logging.getLogger(__name__)
settings = get_settings()

webhook_sender = WebhookSender(settings=settings)

payment_processor = PaymentProcessor(
    session_factory=async_session_factory,
    payment_gateway=PaymentGatewayEmulator(settings),
    webhook_sender=webhook_sender,
)


def get_processing_attempt(message: RabbitMessage) -> int:
    raw_attempt = message.headers.get(PROCESSING_ATTEMPT_HEADER, 1)

    try:
        attempt = int(raw_attempt)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid processing attempt header",
            extra={"raw_attempt": raw_attempt},
        )
        return 1

    return max(1, attempt)


async def publish_retry(
    *,
    event: PaymentCreatedEvent,
    message: RabbitMessage,
    failed_attempt: int,
) -> None:
    retry_bucket = select_retry_bucket(failed_attempt)

    confirmation = await broker.publish(
        event.model_dump(mode="json"),
        queue=retry_bucket.queue,
        headers={
            ORIGINAL_EVENT_ID_HEADER: str(event.event_id),
            PROCESSING_ATTEMPT_HEADER: failed_attempt + 1,
        },
        message_id=message.message_id or str(event.event_id),
        correlation_id=message.correlation_id or str(event.payment_id),
        message_type=event.event_type.value,
        timestamp=datetime.now(UTC),
        persist=True,
        mandatory=True,
        timeout=settings.rabbitmq_publish_timeout_seconds,
    )

    if confirmation is None:
        raise RuntimeError("RabbitMQ did not confirm retry publication")

    logger.info(
        "Payment event scheduled for retry",
        extra={
            "payment_id": str(event.payment_id),
            "event_id": str(event.event_id),
            "failed_attempt": failed_attempt,
            "next_attempt": failed_attempt + 1,
            "retry_delay_ms": retry_bucket.delay_milliseconds,
        },
    )


async def retry_or_send_to_dlq(
    *,
    event: PaymentCreatedEvent,
    message: RabbitMessage,
    failed_attempt: int,
) -> None:
    if failed_attempt >= settings.processing_max_attempts:
        logger.error(
            "Payment event exhausted processing attempts",
            extra={
                "payment_id": str(event.payment_id),
                "event_id": str(event.event_id),
                "attempt": failed_attempt,
            },
        )
        await message.reject(requeue=False)
        return

    try:
        await publish_retry(
            event=event,
            message=message,
            failed_attempt=failed_attempt,
        )
    except Exception:
        logger.exception(
            "Failed to publish payment retry",
            extra={
                "payment_id": str(event.payment_id),
                "event_id": str(event.event_id),
                "attempt": failed_attempt,
            },
        )
        await message.nack(requeue=True)
        return

    await message.ack()


@broker.subscriber(
    payments_queue,
    payments_exchange,
    ack_policy=AckPolicy.MANUAL,
)
async def consume_payment_event(
    payload: Any,
    message: RabbitMessage,
) -> None:
    try:
        event = PaymentCreatedEvent.model_validate(payload)
    except ValidationError:
        logger.exception(
            "Invalid payment event received",
            extra={"message_id": message.message_id},
        )
        await message.reject(requeue=False)
        return

    attempt = get_processing_attempt(message)

    logger.info(
        "Payment event processing started",
        extra={
            "payment_id": str(event.payment_id),
            "event_id": str(event.event_id),
            "attempt": attempt,
        },
    )

    try:
        await payment_processor.process(event)

    except PermanentProcessingError as error:
        logger.error(
            "Permanent payment processing error",
            extra={
                "payment_id": str(event.payment_id),
                "event_id": str(event.event_id),
                "attempt": attempt,
                "error": str(error),
            },
        )
        await message.reject(requeue=False)

    except RetryableProcessingError as error:
        logger.warning(
            "Retryable payment processing error",
            extra={
                "payment_id": str(event.payment_id),
                "event_id": str(event.event_id),
                "attempt": attempt,
                "error": str(error),
            },
        )
        await retry_or_send_to_dlq(
            event=event,
            message=message,
            failed_attempt=attempt,
        )

    except Exception:
        logger.exception(
            "Unexpected payment processing error",
            extra={
                "payment_id": str(event.payment_id),
                "event_id": str(event.event_id),
                "attempt": attempt,
            },
        )
        await retry_or_send_to_dlq(
            event=event,
            message=message,
            failed_attempt=attempt,
        )

    else:
        await message.ack()

        logger.info(
            "Payment event processed successfully",
            extra={
                "payment_id": str(event.payment_id),
                "event_id": str(event.event_id),
                "attempt": attempt,
            },
        )


async def run_consumer() -> None:
    configure_logging(settings.log_level)

    await broker.connect()
    await declare_broker_topology(broker)

    try:
        await broker.start()
        logger.info("Payment consumer started")
        await asyncio.Event().wait()
    finally:
        await webhook_sender.close()
        await broker.stop()
        await dispose_database_engine()


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run_consumer())


if __name__ == "__main__":
    main()