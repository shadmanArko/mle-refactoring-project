"""Health, supported zip codes and facts the web page needs."""

import logging

from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from kc_house.api.deps import Estimator
from kc_house.config import ESTIMATE_INPUTS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health(request: Request, response: Response, service: Estimator) -> dict:
    """Ready when the model is loaded. The database is reported, not required."""
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        logger.warning("database unavailable")
        database = "unavailable"
    return {
        "status": "ok",
        "model": service.info["model_version"],
        "database": database,
    }


@router.get("/zipcodes")
def zipcodes(service: Estimator) -> list[int]:
    """Zip codes the estimator was trained on."""
    return service.zipcodes


@router.get("/meta")
def meta(request: Request, service: Estimator) -> dict:
    """Facts shown on the web page: model quality, inputs and links."""
    return {
        "inputs": ESTIMATE_INPUTS,
        "model": service.info,
        "github_url": request.app.state.settings.github_url,
    }
