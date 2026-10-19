from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import EventType


class PaymentCreatedEvent(BaseModel):
    """Versioned integration event published to payments.new."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_type: EventType = EventType.PAYMENT_CREATED
    event_version: Literal[1] = 1
    occurred_at: datetime
    payment_id: UUID