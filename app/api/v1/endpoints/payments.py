import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.payment import PaymentService
from app.core.exceptions import RequestDataValidationError
from app.db.session import get_session
from app.schemas.common import ErrorResponse
from app.schemas.payment import (
    PaymentAcceptedResponse,
    PaymentCreateRequest,
    PaymentDetailResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
)


@router.post(
    "",
    response_model=PaymentAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing or invalid API key",
        },
        409: {
            "model": ErrorResponse,
            "description": (
                "Idempotency key was used with another request"
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "Request validation failed",
        },
    },
    summary="Create an asynchronous payment",
)
async def create_payment(
    request: PaymentCreateRequest,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentAcceptedResponse:
    if not idempotency_key.strip():
        raise RequestDataValidationError(
            details={
                "field": "Idempotency-Key",
                "reason": "Header must not contain only whitespace",
            }
        )

    service = PaymentService(session)
    result = await service.create_payment(
        request=request,
        idempotency_key=idempotency_key,
    )

    logger.info(
        "Payment request accepted",
        extra={
            "payment_id": str(result.payment.id),
            "payment_status": result.payment.status.value,
            "idempotent_replay": not result.created,
        },
    )

    return PaymentAcceptedResponse.from_payment(result.payment)


@router.get(
    "/{payment_id}",
    response_model=PaymentDetailResponse,
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Missing or invalid API key",
        },
        404: {
            "model": ErrorResponse,
            "description": "Payment was not found",
        },
        422: {
            "model": ErrorResponse,
            "description": "Request validation failed",
        },
    },
    summary="Get payment details",
)
async def get_payment(
    payment_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentDetailResponse:
    service = PaymentService(session)
    payment = await service.get_payment(payment_id)

    return PaymentDetailResponse.from_payment(payment)