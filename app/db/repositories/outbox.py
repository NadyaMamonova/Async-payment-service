from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.outbox import OutboxEvent


class OutboxRepository:
    """Database operations for transactional outbox events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: OutboxEvent) -> OutboxEvent:
        self._session.add(event)
        await self._session.flush()
        return event

    async def claim_pending_batch(
        self,
        *,
        current_time: datetime,
        claimed_until: datetime,
        claim_id: UUID,
        batch_size: int,
    ) -> list[OutboxEvent]:
        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.published_at.is_(None),
                OutboxEvent.next_attempt_at <= current_time,
                or_(
                    OutboxEvent.claimed_until.is_(None),
                    OutboxEvent.claimed_until <= current_time,
                ),
            )
            .order_by(OutboxEvent.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )

        result = await self._session.execute(statement)
        events = list(result.scalars().all())

        for event in events:
            event.claim_id = claim_id
            event.claimed_until = claimed_until

        await self._session.flush()
        return events

    async def mark_published(
        self,
        *,
        event_id: UUID,
        claim_id: UUID,
        published_at: datetime,
    ) -> bool:
        statement = (
            update(OutboxEvent)
            .where(
                OutboxEvent.id == event_id,
                OutboxEvent.claim_id == claim_id,
                OutboxEvent.published_at.is_(None),
            )
            .values(
                published_at=published_at,
                claim_id=None,
                claimed_until=None,
                last_error=None,
            )
        )

        result = await self._session.execute(statement)
        cursor_result = cast(CursorResult[Any], result)
        return cursor_result.rowcount == 1

    async def mark_failed(
        self,
        *,
        event_id: UUID,
        claim_id: UUID,
        next_attempt_at: datetime,
        error_message: str,
    ) -> bool:
        statement = (
            update(OutboxEvent)
            .where(
                OutboxEvent.id == event_id,
                OutboxEvent.claim_id == claim_id,
                OutboxEvent.published_at.is_(None),
            )
            .values(
                attempts=OutboxEvent.attempts + 1,
                next_attempt_at=next_attempt_at,
                last_error=error_message,
                claim_id=None,
                claimed_until=None,
            )
        )

        result = await self._session.execute(statement)
        cursor_result = cast(CursorResult[Any], result)
        return cursor_result.rowcount == 1