from hashlib import sha256
from typing import Any

import orjson

from app.schemas.payment import PaymentCreateRequest


def build_canonical_payment_payload(
    request: PaymentCreateRequest,
) -> dict[str, Any]:
    """Build a deterministic representation of a payment request."""

    return {
        "amount": format(request.amount, ".2f"),
        "currency": request.currency.value,
        "description": request.description,
        "metadata": request.metadata,
        "webhook_url": str(request.webhook_url),
    }


def calculate_payment_request_fingerprint(
    request: PaymentCreateRequest,
) -> str:
    """Return a stable SHA-256 fingerprint for idempotency comparison."""

    canonical_payload = build_canonical_payment_payload(request)
    serialized_payload = orjson.dumps(
        canonical_payload,
        option=orjson.OPT_SORT_KEYS,
    )
    return sha256(serialized_payload).hexdigest()