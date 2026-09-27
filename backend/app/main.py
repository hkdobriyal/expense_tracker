"""FastAPI application entry point: ``uvicorn app.main:app --reload``"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import get_engine
from .money import MoneyError
from .routers import ai, alerting, analytics, auth, integrations, ledger, planning, realtime, system, transactions
from .services.banking import ProviderError
from .services.transactions import TransactionError

log = logging.getLogger("hisaab")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    get_engine()
    if settings.auto_migrate:
        from .migrations import upgrade_database

        upgrade_database()
    log.info("API ready (data dir: %s)", settings.data_dir)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=f"{settings.app_name} API", version="2.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(TransactionError)
    async def _txn_error(_request: Request, exc: TransactionError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(MoneyError)
    async def _money_error(_request: Request, exc: MoneyError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def _provider_error(_request: Request, exc: ProviderError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        # Readable messages ("amount: Input should be a valid decimal") without echoing request bodies back.
        errors = [f"{'.'.join(str(p) for p in e['loc'][1:]) or 'body'}: {e['msg']}" for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": "; ".join(errors[:5]), "errors": errors})

    for module in (auth, ledger, transactions, planning, analytics, integrations, alerting, realtime, ai, system):
        app.include_router(module.router)
    return app


app = create_app()
