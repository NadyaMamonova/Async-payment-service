from secrets import compare_digest
from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyHeader

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


async def require_api_key(
    provided_api_key: Annotated[str | None, Security(api_key_header)],
) -> None:
    """Authenticate a request using a timing-safe comparison."""

    if provided_api_key is None:
        raise AuthenticationError()

    expected_api_key = get_settings().api_key.get_secret_value()

    if not compare_digest(provided_api_key, expected_api_key):
        raise AuthenticationError()