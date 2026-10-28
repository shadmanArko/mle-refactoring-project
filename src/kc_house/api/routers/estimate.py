"""Price estimates from six answers."""

from fastapi import APIRouter

from kc_house.api.deps import Estimator
from kc_house.api.model_service import Estimate, EstimatorService
from kc_house.api.schemas import EstimateRequest, EstimateResponse

router = APIRouter(prefix="/api", tags=["estimate"])

NOTE = (
    "A rough guide from 2014-2015 King County sales, not an appraisal. "
    "It cannot see lot size, condition, view or renovations."
)


def build_response(result: Estimate, service: EstimatorService) -> EstimateResponse:
    return EstimateResponse(
        estimate=result.price,
        low=result.low,
        high=result.high,
        coverage=service.info["range_coverage"],
        typical_error_pct=round(service.info["typical_error_pct"], 1),
        model_version=service.info["model_version"],
        note=NOTE,
    )


@router.post("/estimate", response_model=EstimateResponse)
def estimate_price(request: EstimateRequest, service: Estimator) -> EstimateResponse:
    """Estimate a sale price from six answers about the house."""
    answers = request.model_dump() | {"waterfront": int(request.waterfront)}
    return build_response(service.estimate(answers), service)
