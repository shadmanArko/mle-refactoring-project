"""Shared request dependencies."""

import secrets
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from kc_house.api.model_service import EstimatorService
from kc_house.api.settings import Settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_estimator(request: Request) -> EstimatorService:
    return request.app.state.estimator


def get_session(request: Request) -> Generator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def require_write_access(
    settings: Annotated[Settings, Depends(get_settings)],
    supplied: Annotated[str | None, Depends(api_key_header)],
) -> None:
    """Allow writes only with the configured key; refuse everything if none is set."""
    if settings.api_key is None:
        if settings.open_writes:
            return
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Writes are disabled on this deployment."
        )
    expected = settings.api_key.get_secret_value().encode()
    if supplied is None or not secrets.compare_digest(supplied.encode(), expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid API key.")


DatabaseSession = Annotated[Session, Depends(get_session)]
Estimator = Annotated[EstimatorService, Depends(get_estimator)]
WriteAccess = Depends(require_write_access)
