from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.application.services.webhook import WebhookSigner
from mock_webhook.security import (
    WebhookAuthenticationError,
    WebhookSignatureVerifier,
)

TEST_SECRET = "unit-test-webhook-signing-secret-at-least-32-characters"
EVENT_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
CURRENT_TIME = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
BODY = b'{"status":"succeeded"}'


def test_receiver_accepts_signature_created_by_sender() -> None:
    signer = WebhookSigner(TEST_SECRET)
    verifier = WebhookSignatureVerifier(
        secret=TEST_SECRET,
        timestamp_tolerance_seconds=300,
    )

    headers = signer.build_headers(
        body=BODY,
        event_id=EVENT_ID,
        current_time=CURRENT_TIME,
    )

    verified_event_id = verifier.verify(
        body=BODY,
        webhook_id=headers["X-Webhook-Id"],
        timestamp=headers["X-Webhook-Timestamp"],
        signature=headers["X-Webhook-Signature"],
        current_time=CURRENT_TIME,
    )

    assert verified_event_id == EVENT_ID


def test_modified_body_invalidates_signature() -> None:
    signer = WebhookSigner(TEST_SECRET)
    verifier = WebhookSignatureVerifier(
        secret=TEST_SECRET,
        timestamp_tolerance_seconds=300,
    )

    headers = signer.build_headers(
        body=BODY,
        event_id=EVENT_ID,
        current_time=CURRENT_TIME,
    )

    with pytest.raises(
        WebhookAuthenticationError,
        match="signature is invalid",
    ):
        verifier.verify(
            body=b'{"status":"failed"}',
            webhook_id=headers["X-Webhook-Id"],
            timestamp=headers["X-Webhook-Timestamp"],
            signature=headers["X-Webhook-Signature"],
            current_time=CURRENT_TIME,
        )


def test_expired_signature_is_rejected() -> None:
    signer = WebhookSigner(TEST_SECRET)
    verifier = WebhookSignatureVerifier(
        secret=TEST_SECRET,
        timestamp_tolerance_seconds=300,
    )

    headers = signer.build_headers(
        body=BODY,
        event_id=EVENT_ID,
        current_time=CURRENT_TIME,
    )

    with pytest.raises(
        WebhookAuthenticationError,
        match="outside the allowed time window",
    ):
        verifier.verify(
            body=BODY,
            webhook_id=headers["X-Webhook-Id"],
            timestamp=headers["X-Webhook-Timestamp"],
            signature=headers["X-Webhook-Signature"],
            current_time=CURRENT_TIME + timedelta(seconds=301),
        )