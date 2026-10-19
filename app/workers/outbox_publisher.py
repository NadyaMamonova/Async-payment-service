import asyncio
import logging
from contextlib import suppress

from app.application.services.outbox_publisher import OutboxPublisher
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import async_session_factory, dispose_database_engine
from app.messaging.broker import broker, declare_broker_topology

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_outbox_publisher() -> None:
    configure_logging(settings.log_level)

    await broker.connect()
    await declare_broker_topology(broker)

    publisher = OutboxPublisher(
        session_factory=async_session_factory,
        broker=broker,
        settings=settings,
    )

    logger.info("Outbox publisher started")

    try:
        while True:
            try:
                result = await publisher.publish_pending_batch()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Outbox polling iteration failed")
                await asyncio.sleep(
                    settings.outbox_poll_interval_seconds
                )
                continue

            if result.claimed == 0:
                await asyncio.sleep(
                    settings.outbox_poll_interval_seconds
                )
    finally:
        await broker.stop()
        await dispose_database_engine()
        logger.info("Outbox publisher stopped")


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run_outbox_publisher())


if __name__ == "__main__":
    main()