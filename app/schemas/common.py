from typing import Any, Literal

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"