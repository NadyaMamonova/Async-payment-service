import asyncio
import logging
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import ValidationError

from app.application.services.webhook import (
    WEBHOOK_ID_HEADER,
    WEBHOOK_SIGNATURE_HEADER,
    WEBHOOK_TIMESTAMP_HEADER,
)
from app.core.logging import configure_logging
from app.schemas.webhook import PaymentProcessedWebhook
from mock_webhook.config import get_mock_webhook_settings
from mock_webhook.security import (
    WebhookAuthenticationError,
    WebhookSignatureVerifier,
)

settings = get_mock_webhook_settings()
configure_logging("INFO")

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mock Payment Webhook Receiver",
    version="1.0.0",
)

signature_verifier = WebhookSignatureVerifier(
    secret=settings.webhook_signing_secret.get_secret_value(),
    timestamp_tolerance_seconds=(
        settings.mock_webhook_timestamp_tolerance_seconds
    ),
)


class DeliveryAttemptTracker:
    """Keep per-event delivery counters for the local demo service."""

    def __init__(self) -> None:
        self._attempts: dict[UUID, int] = {}
        self._lock = asyncio.Lock()

    async def register_attempt(self, event_id: UUID) -> int:
        async with self._lock:
            attempt = self._attempts.get(event_id, 0) + 1
            self._attempts[event_id] = attempt
            return attempt


delivery_attempt_tracker = DeliveryAttemptTracker()


@app.get("/health/live", include_in_schema=False)
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def receive_webhook(
    request: Request,
    x_webhook_id: Annotated[
        str,
        Header(alias=WEBHOOK_ID_HEADER),
    ],
    x_webhook_timestamp: Annotated[
        str,
        Header(alias=WEBHOOK_TIMESTAMP_HEADER),
    ],
    x_webhook_signature: Annotated[
        str,
        Header(alias=WEBHOOK_SIGNATURE_HEADER),
    ],
) -> Response:
    body = await request.body()

    try:
        header_event_id = signature_verifier.verify(
            body=body,
            webhook_id=x_webhook_id,
            timestamp=x_webhook_timestamp,
            signature=x_webhook_signature,
        )
    except WebhookAuthenticationError as error:
        logger.warning(
            "Webhook authentication failed",
            extra={"error": str(error)},
        )
        raise HTTPException(
            status_code=401,
            detail=str(error),
        ) from None

    try:
        webhook = PaymentProcessedWebhook.model_validate_json(body)
    except ValidationError as error:
        logger.warning(
            "Invalid webhook payload",
            extra={"error_count": error.error_count()},
        )
        raise HTTPException(
            status_code=422,
            detail="Invalid webhook payload",
        ) from None

    if webhook.event_id != header_event_id:
        raise HTTPException(
            status_code=401,
            detail="Webhook event ID does not match the signed request",
        )

    delivery_attempt = (
        await delivery_attempt_tracker.register_attempt(
            webhook.event_id
        )
    )

    should_fail = (
        delivery_attempt
        <= settings.mock_webhook_failures_before_success
    )

    response_status = (
        settings.mock_webhook_failure_status
        if should_fail
        else settings.mock_webhook_success_status
    )

    logger.info(
        "Webhook received",
        extra={
            "event_id": str(webhook.event_id),
            "payment_id": str(webhook.payment_id),
            "payment_status": webhook.status.value,
            "delivery_attempt": delivery_attempt,
            "response_status": response_status,
        },
    )

    return Response(status_code=response_status)