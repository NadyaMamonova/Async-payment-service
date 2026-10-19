import httpx
import pytest

from app.application.services.webhook import WebhookSender
from app.core.config import Settings
from app.core.exceptions import (
    PermanentWebhookError,
    RetryableWebhookError,
)
from app.db.models.payment import Payment


def build_mock_transport(
    status_code: int,
) -> httpx.MockTransport:
    def handle_request(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Webhook-Signature"].startswith("v1=")
        assert request.headers["X-Webhook-Id"]
        assert request.headers["X-Webhook-Timestamp"]

        return httpx.Response(
            status_code=status_code,
            request=request,
        )

    return httpx.MockTransport(handle_request)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [200, 201, 202, 204, 299])
async def test_any_2xx_status_is_successful(
    status_code: int,
    settings: Settings,
    processed_payment: Payment,
) -> None:
    async with httpx.AsyncClient(
        transport=build_mock_transport(status_code)
    ) as http_client:
        sender = WebhookSender(
            settings=settings,
            http_client=http_client,
        )

        await sender.send_payment_processed(processed_payment)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [408, 425, 429, 500, 502, 503, 504],
)
async def test_temporary_http_status_is_retryable(
    status_code: int,
    settings: Settings,
    processed_payment: Payment,
) -> None:
    async with httpx.AsyncClient(
        transport=build_mock_transport(status_code)
    ) as http_client:
        sender = WebhookSender(
            settings=settings,
            http_client=http_client,
        )

        with pytest.raises(RetryableWebhookError):
            await sender.send_payment_processed(processed_payment)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [400, 401, 403, 404, 409, 422],
)
async def test_permanent_http_status_is_not_retried(
    status_code: int,
    settings: Settings,
    processed_payment: Payment,
) -> None:
    async with httpx.AsyncClient(
        transport=build_mock_transport(status_code)
    ) as http_client:
        sender = WebhookSender(
            settings=settings,
            http_client=http_client,
        )

        with pytest.raises(PermanentWebhookError):
            await sender.send_payment_processed(processed_payment)