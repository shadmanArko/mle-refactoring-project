"""FastAPI application factory.

Run locally:  ``uv run uvicorn kc_house.api.main:create_app --factory``
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import (
    InterfaceError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import sessionmaker

from kc_house.api.db import Base, make_engine
from kc_house.api.model_service import EstimatorService, UnknownZipcodeError
from kc_house.api.observability import configure_logging, request_logging
from kc_house.api.routers import estimate, houses, meta, pages
from kc_house.api.secrets import resolve_secrets
from kc_house.api.settings import Settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        # Fail fast: an app that cannot estimate should never look healthy, and one
        # whose configured secrets cannot be read should not silently run without them.
        resolved = resolve_secrets(settings)
        app.state.settings = resolved
        app.state.estimator = EstimatorService(resolved.model_dir)
        engine = make_engine(resolved.database_url)
        app.state.engine = engine
        app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
        if resolved.create_tables:
            try:
                Base.metadata.create_all(engine)
            except SQLAlchemyError:
                # Estimates do not need the database, so keep serving them.
                logger.warning("could not create tables; database unavailable")
        yield
        engine.dispose()

    app = FastAPI(
        title="King County house price estimator",
        description="Estimate a house price from six answers and manage saved houses.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.middleware("http")(request_logging)
    app.include_router(pages.router)
    app.include_router(meta.router)
    app.include_router(estimate.router)
    app.include_router(houses.router)

    @app.exception_handler(UnknownZipcodeError)
    async def unknown_zipcode(_: Request, error: UnknownZipcodeError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    @app.exception_handler(PoolTimeoutError)
    async def database_unavailable(_: Request, __: Exception) -> JSONResponse:
        logger.exception("database error")
        return JSONResponse(
            status_code=503, content={"detail": "Database temporarily unavailable."}
        )

    return app
