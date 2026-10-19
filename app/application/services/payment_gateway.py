import asyncio
from hashlib import sha256
from random import Random, SystemRandom
from typing import Protocol
from uuid import UUID

from app.core.config import Settings
from app.core.enums import Currency, PaymentStatus


class PaymentGateway(Protocol):
    """Interface implemented by external payment providers."""

    async def process_payment(
        self,
        *,
        payment_id: UUID,
        amount: str,
        currency: Currency,
    ) -> PaymentStatus:
        """Process a payment and return its final business status."""


class PaymentGatewayEmulator:
    """Deterministic idempotent emulator with configurable latency."""

    def __init__(
        self,
        settings: Settings,
        *,
        random_source: Random | None = None,
    ) -> None:
        self._settings = settings
        self._random = random_source or SystemRandom()

    async def process_payment(
        self,
        *,
        payment_id: UUID,
        amount: str,
        currency: Currency,
    ) -> PaymentStatus:
        del amount, currency

        delay = float(
            self._random.uniform(
                self._settings.payment_processing_min_delay_seconds,
                self._settings.payment_processing_max_delay_seconds,
            )
        )
        await asyncio.sleep(delay)

        score = self._calculate_deterministic_score(payment_id)

        if score < self._settings.payment_success_rate:
            return PaymentStatus.SUCCEEDED

        return PaymentStatus.FAILED

    @staticmethod
    def _calculate_deterministic_score(payment_id: UUID) -> float:
        digest = sha256(payment_id.bytes).digest()
        integer_value = int.from_bytes(
            digest[:8],
            byteorder="big",
            signed=False,
        )
        return integer_value / (2**64)