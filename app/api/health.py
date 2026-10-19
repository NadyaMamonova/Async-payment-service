import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DependencyUnavailableError
from app.db.session import get_session
from app.schemas.common import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get(
    "/health/live",
    response_model=HealthResponse,
    summary="Check whether the API process is alive",
)
async def liveness() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check whether the API is ready to accept requests",
)
async def readiness(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        logger.warning("Database readiness check failed")
        raise DependencyUnavailableError(
            "Database is unavailable"
        ) from error

    return HealthResponse()