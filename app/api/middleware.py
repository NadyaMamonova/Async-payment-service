from uuid import UUID, uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import reset_request_id, set_request_id


class RequestContextMiddleware:
    """Attach a safe correlation identifier to every HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = self._resolve_request_id(headers.get("X-Request-ID"))
        token = set_request_id(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self._app(scope, receive, send_with_request_id)
        finally:
            reset_request_id(token)

    @staticmethod
    def _resolve_request_id(value: str | None) -> str:
        if value is None:
            return str(uuid4())

        try:
            return str(UUID(value))
        except ValueError:
            return str(uuid4())