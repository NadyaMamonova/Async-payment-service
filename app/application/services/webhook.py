import hmac
from datetime import UTC, datetime
from hashlib import sha256
from typing import Final
from uuid import UUID

import httpx
import orjson

from app.application.services.webhook_security import (
    WebhookUrlValidator,
)
from app.core.config import Settings
from app.core.exceptions import (
    PermanentWebhookError,
    RetryableWebhookError,
)
from app.db.models.payment import Payment
from app.schemas.webhook import PaymentProcessedWebhook

WEBHOOK_ID_HEADER: Final = "X-Webhook-Id"
WEBHOOK_TIMESTAMP_HEADER: Final = "X-Webhook-Timestamp"
WEBHOOK_SIGNATURE_HEADER: Final = "X-Webhook-Signature"

RETRYABLE_HTTP_STATUSES: Final = frozenset({408, 425, 429})


class WebhookSigner:
    """Build HMAC-SHA256 signatures over exact request bytes."""

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def build_headers(
        self,
        *,
        body: bytes,
        event_id: UUID,
        current_time: datetime | None = None,
    ) -> dict[str, str]:
        timestamp = int(
            (current_time or datetime.now(UTC)).timestamp()
        )
        signed_payload = (
            str(timestamp).encode("ascii")
            + b"."
            + body
        )
        digest = hmac.new(
            self._secret,
            signed_payload,
            sha256,
        ).hexdigest()

        return {
            "Content-Type": "application/json",
            "User-Agent": "async-payment-service/1.0",
            WEBHOOK_ID_HEADER: str(event_id),
            WEBHOOK_TIMESTAMP_HEADER: str(timestamp),
            WEBHOOK_SIGNATURE_HEADER: f"v1={digest}",
        }


class WebhookSender:
    """Validate, sign and deliver payment webhooks."""

    def __init__(
        self,
        *,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._url_validator = WebhookUrlValidator(settings)
        self._signer = WebhookSigner(
            settings.webhook_signing_secret.get_secret_value()
        )
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
        )

    async def send_payment_processed(
        self,
        payment: Payment,
    ) -> None:
        await self._url_validator.validate(payment.webhook_url)

        webhook = PaymentProcessedWebhook.from_payment(payment)
        body = orjson.dumps(
            webhook.model_dump(mode="json"),
            option=orjson.OPT_SORT_KEYS,
        )
        headers = self._signer.build_headers(
            body=body,
            event_id=webhook.event_id,
        )

        try:
            response = await self._http_client.post(
                payment.webhook_url,
                content=body,
                headers=headers,
                timeout=self._settings.webhook_timeout_seconds,
            )
        except httpx.RequestError as error:
            raise RetryableWebhookError(
                f"Webhook request failed: {type(error).__name__}"
            ) from error

        if 200 <= response.status_code < 300:
            return

        if (
            response.status_code in RETRYABLE_HTTP_STATUSES
            or response.status_code >= 500
        ):
            raise RetryableWebhookError(
                f"Webhook returned retryable HTTP status "
                f"{response.status_code}"
            )

        raise PermanentWebhookError(
            f"Webhook returned permanent HTTP status "
            f"{response.status_code}"
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()