from dataclasses import dataclass
from random import Random, SystemRandom

from faststream.rabbit import RabbitExchange, RabbitQueue
from faststream.rabbit.schemas import ExchangeType, QueueType

from app.core.config import Settings, get_settings
from app.messaging.constants import (
    PAYMENTS_DEAD_LETTER_EXCHANGE_NAME,
    PAYMENTS_DEAD_LETTER_QUEUE_NAME,
    PAYMENTS_DEAD_LETTER_ROUTING_KEY,
    PAYMENTS_EXCHANGE_NAME,
    PAYMENTS_NEW_ROUTING_KEY,
    PAYMENTS_QUEUE_NAME,
)

payments_exchange = RabbitExchange(
    name=PAYMENTS_EXCHANGE_NAME,
    type=ExchangeType.DIRECT,
    durable=True,
)

payments_dead_letter_exchange = RabbitExchange(
    name=PAYMENTS_DEAD_LETTER_EXCHANGE_NAME,
    type=ExchangeType.DIRECT,
    durable=True,
)

payments_queue = RabbitQueue(
    name=PAYMENTS_QUEUE_NAME,
    queue_type=QueueType.QUORUM,
    durable=True,
    routing_key=PAYMENTS_NEW_ROUTING_KEY,
    arguments={
        "x-dead-letter-exchange": PAYMENTS_DEAD_LETTER_EXCHANGE_NAME,
        "x-dead-letter-routing-key": PAYMENTS_DEAD_LETTER_ROUTING_KEY,
    },
)

payments_dead_letter_queue = RabbitQueue(
    name=PAYMENTS_DEAD_LETTER_QUEUE_NAME,
    queue_type=QueueType.QUORUM,
    durable=True,
    routing_key=PAYMENTS_DEAD_LETTER_ROUTING_KEY,
)


@dataclass(frozen=True, slots=True)
class RetryQueueBucket:
    """One broker-side delay option for a processing attempt."""

    failed_attempt: int
    delay_milliseconds: int
    queue: RabbitQueue


def build_retry_queue_buckets(
    settings: Settings,
) -> dict[int, tuple[RetryQueueBucket, ...]]:
    """Create exponential retry queues with discrete jitter buckets."""

    buckets_by_attempt: dict[int, tuple[RetryQueueBucket, ...]] = {}

    for failed_attempt in range(1, settings.processing_max_attempts):
        exponential_delay_seconds = (
            settings.retry_base_delay_seconds
            * (2 ** (failed_attempt - 1))
        )

        jitter_factors = (
            1 - settings.retry_jitter_ratio,
            1.0,
            1 + settings.retry_jitter_ratio,
        )

        delay_values = sorted(
            {
                max(
                    1,
                    round(
                        exponential_delay_seconds
                        * jitter_factor
                        * 1000
                    ),
                )
                for jitter_factor in jitter_factors
            }
        )

        attempt_buckets = tuple(
            RetryQueueBucket(
                failed_attempt=failed_attempt,
                delay_milliseconds=delay_milliseconds,
                queue=RabbitQueue(
                    name=(
                        "payments.retry."
                        f"attempt-{failed_attempt}."
                        f"{delay_milliseconds}ms"
                    ),
                    queue_type=QueueType.CLASSIC,
                    durable=True,
                    arguments={
                        "x-message-ttl": delay_milliseconds,
                        "x-dead-letter-exchange": PAYMENTS_EXCHANGE_NAME,
                        "x-dead-letter-routing-key": (
                            PAYMENTS_NEW_ROUTING_KEY
                        ),
                    },
                ),
            )
            for delay_milliseconds in delay_values
        )

        buckets_by_attempt[failed_attempt] = attempt_buckets

    return buckets_by_attempt


retry_buckets_by_failed_attempt = build_retry_queue_buckets(
    get_settings()
)

_system_random = SystemRandom()


def select_retry_bucket(
    failed_attempt: int,
    *,
    random_source: Random | None = None,
) -> RetryQueueBucket:
    """Randomly select a jitter bucket for the failed attempt."""

    try:
        available_buckets = retry_buckets_by_failed_attempt[
            failed_attempt
        ]
    except KeyError as error:
        raise ValueError(
            f"No retry queues configured for failed attempt "
            f"{failed_attempt}"
        ) from error

    generator = random_source or _system_random
    return generator.choice(available_buckets)


def get_all_retry_buckets() -> tuple[RetryQueueBucket, ...]:
    return tuple(
        bucket
        for attempt_buckets in retry_buckets_by_failed_attempt.values()
        for bucket in attempt_buckets
    )