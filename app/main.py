import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.middleware import RequestContextMiddleware
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_database_engine

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(settings.log_level)

    logger.info(
        "Application started",
        extra={"environment": settings.app_env},
    )

    yield

    await dispose_database_engine()
    logger.info("Application stopped")


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        default_response_class=JSONResponse,
        lifespan=lifespan,
    )

    application.add_middleware(RequestContextMiddleware)
    register_exception_handlers(application)

    application.include_router(health_router)
    application.include_router(api_v1_router)

    return application


app = create_application()