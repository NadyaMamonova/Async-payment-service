import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_request_id
from app.core.exceptions import ApplicationError

logger = logging.getLogger(__name__)


def build_error_content(
    *,
    code: str,
    message: str,
    details: Any | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details is not None:
        detail["details"] = details

    return {"detail": detail}


def register_exception_handlers(app: FastAPI) -> None:
    """Register the service-wide public error contract."""

    @app.exception_handler(ApplicationError)
    async def handle_application_error(
        request: Request,
        error: ApplicationError,
    ) -> JSONResponse:
        headers = None
        if error.status_code == 401:
            headers = {"WWW-Authenticate": "ApiKey"}

        logger.info(
            "Application request rejected",
            extra={
                "error_code": error.code,
                "status_code": error.status_code,
                "method": request.method,
                "path": request.url.path,
            },
        )

        return JSONResponse(
            status_code=error.status_code,
            content=build_error_content(
                code=error.code,
                message=error.message,
                details=error.details,
            ),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        validation_errors = [
            {
                "location": [
                    str(location_part)
                    for location_part in item["loc"]
                ],
                "message": item["msg"],
                "type": item["type"],
            }
            for item in error.errors()
        ]

        logger.info(
            "Request validation failed",
            extra={
                "status_code": 422,
                "method": request.method,
                "path": request.url.path,
            },
        )

        return JSONResponse(
            status_code=422,
            content=build_error_content(
                code="validation_error",
                message="Request validation failed",
                details=validation_errors,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        error_codes = {
            404: "route_not_found",
            405: "method_not_allowed",
        }

        return JSONResponse(
            status_code=error.status_code,
            content=build_error_content(
                code=error_codes.get(error.status_code, "http_error"),
                message=str(error.detail),
            ),
            headers=error.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled application error",
            extra={
                "method": request.method,
                "path": request.url.path,
                "request_id": get_request_id(),
            },
        )

        return JSONResponse(
            status_code=500,
            content=build_error_content(
                code="internal_error",
                message="An unexpected error occurred",
            ),
        )