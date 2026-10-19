import logging

from faststream.rabbit import Channel, RabbitBroker

from app.core.config import get_settings
from app.messaging.constants import (
    PAYMENTS_DEAD_LETTER_ROUTING_KEY,
    PAYMENTS_NEW_ROUTING_KEY,
)
from app.messaging.topology import (
    get_all_retry_buckets,
    payments_dead_letter_exchange,
    payments_dead_letter_queue,
    payments_exchange,
    payments_queue,
)

logger = logging.getLogger(__name__)
settings = get_settings()

broker = RabbitBroker(
    settings.rabbitmq_url,
    fail_fast=True,
    reconnect_interval=5.0,
    default_channel=Channel(
        prefetch_count=1,
        publisher_confirms=True,
        on_return_raises=True,
    ),
)


async def declare_broker_topology(
    target_broker: RabbitBroker,
) -> None:
    """Declare all exchanges, queues and bindings idempotently."""

    declared_payments_exchange = (
        await target_broker.declare_exchange(payments_exchange)
    )
    declared_dead_letter_exchange = (
        await target_broker.declare_exchange(
            payments_dead_letter_exchange
        )
    )

    declared_payments_queue = await target_broker.declare_queue(
        payments_queue
    )
    await declared_payments_queue.bind(
        declared_payments_exchange,
        routing_key=PAYMENTS_NEW_ROUTING_KEY,
    )

    declared_dead_letter_queue = (
        await target_broker.declare_queue(
            payments_dead_letter_queue
        )
    )
    await declared_dead_letter_queue.bind(
        declared_dead_letter_exchange,
        routing_key=PAYMENTS_DEAD_LETTER_ROUTING_KEY,
    )

    retry_buckets = get_all_retry_buckets()
    for retry_bucket in retry_buckets:
        await target_broker.declare_queue(retry_bucket.queue)

    logger.info(
        "RabbitMQ topology declared",
        extra={
            "payments_queue": payments_queue.name,
            "dead_letter_queue": payments_dead_letter_queue.name,
            "retry_queue_count": len(retry_buckets),
        },
    )