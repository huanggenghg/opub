from __future__ import annotations

import logging
import os
import secrets
import sqlite3
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from license_server.config import Settings
from license_server.database import Database
from license_server.limiter import RateLimiter
from license_server.mianbaoduo import MianbaoduoClient
from license_server.service import LicenseService

logger = logging.getLogger("opub.license")


class ActivationRequest(BaseModel):
    device_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    client_nonce: str = Field(min_length=22, max_length=256)
    client_version: str = Field(min_length=1, max_length=64)
    payway: Literal["wechat", "alipay"]


class WebhookRequest(BaseModel):
    type: str
    data: dict[str, Any]


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    """Extract the raw poll token from the Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing poll token")
    return authorization.removeprefix("Bearer ")


def _sanitize_order_id(raw: object) -> str:
    """Flatten an attacker-controlled order id so it cannot forge log lines."""
    return str(raw).replace("\r", "").replace("\n", " ")[:128]


async def service_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """Answer 503 with an opaque request id; log the exception class, never its message."""
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
    """Answer 422 without echoing the rejected values back in the response."""
    details = [
        {key: value for key, value in error.items() if key != "input"}
        for error in exc.errors()
    ]
    # Plain 422 rather than status.HTTP_422_UNPROCESSABLE_ENTITY: newer
    # Starlette deprecates the _ENTITY name, older releases lack _CONTENT.
    return JSONResponse(status_code=422, content={"detail": details})


def create_app(settings: Settings, database: Database, provider: MianbaoduoClient) -> FastAPI:
    """Build the license service app around injected settings, database and provider."""
    database.initialize()
    service = LicenseService(settings, database, provider)
    creation_limiter = RateLimiter(60, 3600)
    creation_ip_limiter = RateLimiter(120, 3600)
    polling_limiter = RateLimiter(180, 600)
    app = FastAPI(title="opub License Service", docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/v1/activation-sessions", status_code=status.HTTP_201_CREATED)
    def create_activation(body: ActivationRequest, request: Request):
        client_ip = request.client.host if request.client else "unknown"
        # The per-IP gate runs before the per-(IP, device) one: device_hash is
        # client-chosen, so without this cap one IP could rotate hashes and
        # create unlimited provider checkouts. A request rejected here never
        # reaches the combined bucket below.
        if not creation_ip_limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="rate limited")
        if not creation_limiter.allow(f"{client_ip}:{body.device_hash}"):
            raise HTTPException(status_code=429, detail="rate limited")
        return service.create_session(body.device_hash, body.payway)

    @app.get("/v1/activation-sessions/{session_id}")
    def get_activation(session_id: str, request: Request, token: str = Depends(bearer_token)):
        client_ip = request.client.host if request.client else "unknown"
        if not polling_limiter.allow(f"{client_ip}:{session_id}"):
            raise HTTPException(status_code=429, detail="rate limited")
        try:
            # get_session hashes the raw token internally; the raw value never
            # reaches the repository or the logs.
            return service.get_session(session_id, token)
        except PermissionError:
            raise HTTPException(status_code=401, detail="invalid poll token")

    @app.post("/v1/webhooks/mianbaoduo")
    def webhook(body: WebhookRequest):
        if body.type == "complaint":
            logger.warning(
                "payment complaint order=%s",
                _sanitize_order_id(body.data.get("out_trade_no", "unknown")),
            )
            return {"status": "ignored"}
        if body.type != "charge_succeeded":
            return {"status": "ignored"}
        order_id = str(body.data.get("out_trade_no", ""))
        result = service.handle_charge_succeeded(order_id)
        # Unknown orders and failed verifications are audit events: they are
        # recorded with the sanitized order id only, never the raw payload.
        if result.get("status") in ("ignored", "verification_failed"):
            logger.warning(
                "charge_succeeded webhook %s order=%s",
                result.get("status"),
                _sanitize_order_id(order_id or "unknown"),
            )
        return result

    # ProviderError and RepositoryError subclass RuntimeError, and Starlette
    # resolves handlers through the exception MRO, so both are covered here.
    # HTTPException is dispatched separately by Starlette, so 401/404/429
    # responses are unaffected.
    app.add_exception_handler(RuntimeError, service_unavailable)
    app.add_exception_handler(sqlite3.Error, service_unavailable)
    # Pydantic error details carry the rejected "input" value; drop it so
    # responses never echo device hashes or other submitted values.
    app.add_exception_handler(RequestValidationError, validation_error)
    return app


def app_from_env() -> FastAPI:
    """Uvicorn entry point: uvicorn license_server.app:app_from_env --factory."""
    settings = Settings.from_env(os.environ)
    database = Database(settings.database_path)
    provider = MianbaoduoClient(
        settings.mbd_app_id, settings.mbd_app_key, settings.payment_return_url
    )
    return create_app(settings, database, provider)
