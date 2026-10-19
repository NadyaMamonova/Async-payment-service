import asyncio
import socket
from ipaddress import ip_address
from urllib.parse import SplitResult, urlsplit

from app.core.config import Settings
from app.core.exceptions import (
    PermanentWebhookError,
    RetryableWebhookError,
)


class WebhookUrlValidator:
    """Reject webhook targets that could reach internal infrastructure."""

    def __init__(self, settings: Settings) -> None:
        self._require_https = settings.webhook_require_https
        self._allowed_private_hosts = {
            host.rstrip(".").casefold()
            for host in settings.webhook_allowed_private_hosts
        }

    async def validate(self, url: str) -> None:
        parsed_url = self._parse_url(url)
        hostname = self._normalize_hostname(parsed_url)

        if parsed_url.username is not None or parsed_url.password is not None:
            raise PermanentWebhookError(
                "Webhook URL must not contain credentials"
            )

        if parsed_url.fragment:
            raise PermanentWebhookError(
                "Webhook URL must not contain a fragment"
            )

        if hostname in self._allowed_private_hosts:
            return

        if self._require_https and parsed_url.scheme != "https":
            raise PermanentWebhookError(
                "Webhook URL must use HTTPS"
            )

        port = self._get_port(parsed_url)
        if port not in (None, 443):
            raise PermanentWebhookError(
                "Public webhook URL must use the default HTTPS port"
            )

        await self._validate_resolved_addresses(
            hostname=hostname,
            port=port or 443,
        )

    @staticmethod
    def _parse_url(url: str) -> SplitResult:
        parsed_url = urlsplit(url)

        if parsed_url.scheme not in {"http", "https"}:
            raise PermanentWebhookError(
                "Webhook URL must use HTTP or HTTPS"
            )

        if parsed_url.hostname is None:
            raise PermanentWebhookError(
                "Webhook URL must contain a hostname"
            )

        return parsed_url

    @staticmethod
    def _normalize_hostname(parsed_url: SplitResult) -> str:
        hostname = parsed_url.hostname
        if hostname is None:
            raise PermanentWebhookError(
                "Webhook URL must contain a hostname"
            )

        return hostname.rstrip(".").casefold()

    @staticmethod
    def _get_port(parsed_url: SplitResult) -> int | None:
        try:
            return parsed_url.port
        except ValueError as error:
            raise PermanentWebhookError(
                "Webhook URL contains an invalid port"
            ) from error

    @staticmethod
    async def _validate_resolved_addresses(
        *,
        hostname: str,
        port: int,
    ) -> None:
        try:
            literal_address = ip_address(hostname)
        except ValueError:
            literal_address = None

        if literal_address is not None:
            if not literal_address.is_global:
                raise PermanentWebhookError(
                    "Webhook URL resolves to a non-public IP address"
                )
            return

        event_loop = asyncio.get_running_loop()

        try:
            address_info = await event_loop.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as error:
            raise RetryableWebhookError(
                "Webhook hostname could not be resolved"
            ) from error

        if not address_info:
            raise RetryableWebhookError(
                "Webhook hostname did not resolve to any address"
            )

        resolved_addresses = {
            str(address[4][0])
            for address in address_info
        }

        for resolved_address in resolved_addresses:
            address = ip_address(resolved_address)

            if not address.is_global:
                raise PermanentWebhookError(
                    "Webhook hostname resolves to a non-public IP address"
                )