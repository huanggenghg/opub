from __future__ import annotations

import logging
import os
import secrets
import sqlite3

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from license_server.config import Settings
from license_server.database import Database
from license_server.limiter import RateLimiter
from license_server.service import (
    ActivationCodeUsed,
    ClientVersionMismatch,
    InvalidActivationCode,
    LicenseService,
)


logger = logging.getLogger("opub.license")

_REDEMPTION_DEVICE_LIMIT = 60
_REDEMPTION_IP_LIMIT = 120
_REDEMPTION_WINDOW_SECONDS = 3600


class CodeActivationRequest(BaseModel):
    device_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_code: str = Field(min_length=1, max_length=64)
    client_version: str = Field(min_length=1, max_length=64)


async def service_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """Return an opaque failure response and keep submitted secrets out of logs."""
    request_id = secrets.token_hex(8)
    logger.error(
        "license service failure request_id=%s route=%s error=%s",
        request_id,
        request.url.path,
        exc.__class__.__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "service unavailable", "request_id": request_id},
    )


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return validation metadata without echoing any rejected input values."""
    details = [
        {key: value for key, value in error.items() if key != "input"}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


def create_app(settings: Settings, database: Database) -> FastAPI:
    """Build the one-route activation-code service."""
    database.initialize()
    service = LicenseService(settings, database)
    ip_limiter = RateLimiter(_REDEMPTION_IP_LIMIT, _REDEMPTION_WINDOW_SECONDS)
    device_limiter = RateLimiter(_REDEMPTION_DEVICE_LIMIT, _REDEMPTION_WINDOW_SECONDS)
    app = FastAPI(
        title="opub License Service",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.post("/v1/code-activations")
    def activate_code(body: CodeActivationRequest, request: Request):
        client_ip = request.client.host if request.client else "unknown"
        if not ip_limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="rate limited")
        if not device_limiter.allow(f"{client_ip}:{body.device_hash}"):
            raise HTTPException(status_code=429, detail="rate limited")

        try:
            return service.redeem(
                body.activation_code,
                body.device_hash,
                body.client_version,
            )
        except InvalidActivationCode as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": exc.code},
            ) from None
        except ActivationCodeUsed as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": exc.code},
            ) from None
        except ClientVersionMismatch as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": exc.code},
            ) from None

    app.add_exception_handler(RuntimeError, service_unavailable)
    app.add_exception_handler(sqlite3.Error, service_unavailable)
    app.add_exception_handler(RequestValidationError, validation_error)
    return app


def app_from_env() -> FastAPI:
    """Uvicorn entry point: uvicorn license_server.app:app_from_env --factory."""
    settings = Settings.from_env(os.environ)
    return create_app(settings, Database(settings.database_path))
