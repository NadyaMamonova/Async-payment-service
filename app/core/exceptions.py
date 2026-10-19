from collections.abc import Mapping
from typing import Any


class ApplicationError(Exception):
    """Base exception safe to expose through the public API."""

    status_code = 500
    code = "internal_error"
    default_message = "An unexpected error occurred"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = dict(details) if details is not None else None
        super().__init__(self.message)


class AuthenticationError(ApplicationError):
    status_code = 401
    code = "authentication_failed"
    default_message = "Missing or invalid API key"


class PaymentNotFoundError(ApplicationError):
    status_code = 404
    code = "payment_not_found"
    default_message = "Payment not found"


class IdempotencyConflictError(ApplicationError):
    status_code = 409
    code = "idempotency_conflict"
    default_message = "Idempotency key was already used with a different request"


class DependencyUnavailableError(ApplicationError):
    status_code = 503
    code = "dependency_unavailable"
    default_message = "A required service dependency is unavailable"


class ProcessingError(Exception):
    """Base error raised while processing an asynchronous payment event."""


class RetryableProcessingError(ProcessingError):
    """A transient failure that may succeed on a later attempt."""


class PermanentProcessingError(ProcessingError):
    """A failure that should be sent directly to the dead-letter queue."""


class RequestDataValidationError(ApplicationError):
    status_code = 422
    code = "validation_error"
    default_message = "Request validation failed"


class RetryableWebhookError(RetryableProcessingError):
    """A temporary webhook failure that should be retried."""


class PermanentWebhookError(PermanentProcessingError):
    """A webhook failure that will not be fixed by retrying."""