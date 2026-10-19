import hmac
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID


class WebhookAuthenticationError(ValueError):
    """Raised when webhook authentication data is invalid."""


class WebhookSignatureVerifier:
    """Verify webhook HMAC signatures and timestamp freshness."""

    def __init__(
        self,
        *,
        secret: str,
        timestamp_tolerance_seconds: int,
    ) -> None:
        self._secret = secret.encode("utf-8")
        self._timestamp_tolerance_seconds = timestamp_tolerance_seconds

    def verify(
        self,
        *,
        body: bytes,
        webhook_id: str,
        timestamp: str,
        signature: str,
        current_time: datetime | None = None,
    ) -> UUID:
        event_id = self._parse_event_id(webhook_id)
        parsed_timestamp = self._parse_timestamp(timestamp)

        now = current_time or datetime.now(UTC)
        current_timestamp = int(now.timestamp())

        if (
            abs(current_timestamp - parsed_timestamp)
            > self._timestamp_tolerance_seconds
        ):
            raise WebhookAuthenticationError(
                "Webhook timestamp is outside the allowed time window"
            )

        signed_payload = (
            str(parsed_timestamp).encode("ascii")
            + b"."
            + body
        )
        expected_digest = hmac.new(
            self._secret,
            signed_payload,
            sha256,
        ).hexdigest()
        expected_signature = f"v1={expected_digest}"

        if not hmac.compare_digest(
            signature,
            expected_signature,
        ):
            raise WebhookAuthenticationError(
                "Webhook signature is invalid"
            )

        return event_id

    @staticmethod
    def _parse_event_id(value: str) -> UUID:
        try:
            return UUID(value)
        except ValueError as error:
            raise WebhookAuthenticationError(
                "X-Webhook-Id is not a valid UUID"
            ) from error

    @staticmethod
    def _parse_timestamp(value: str) -> int:
        try:
            return int(value)
        except ValueError as error:
            raise WebhookAuthenticationError(
                "X-Webhook-Timestamp is invalid"
            ) from error