"""Create, read, update and delete houses."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from kc_house.api.db import House
from kc_house.api.deps import DatabaseSession, Estimator, WriteAccess
from kc_house.api.routers.estimate import build_response
from kc_house.api.schemas import (
    EstimateResponse,
    HouseCreate,
    HouseList,
    HouseOut,
    HouseUpdate,
)

router = APIRouter(prefix="/api/houses", tags=["houses"])


def _get_or_404(session: DatabaseSession, house_id: int) -> House:
    house = session.get(House, house_id)
    if house is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"House {house_id} not found.")
    return house


@router.get("", response_model=HouseList)
def list_houses(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HouseList:
    """List houses, oldest first, one page at a time."""
    total = session.scalar(select(func.count()).select_from(House)) or 0
    rows = session.scalars(
        select(House).order_by(House.id).limit(limit).offset(offset)
    ).all()
    return HouseList(
        items=[HouseOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=HouseOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WriteAccess],
)
def create_house(
    body: HouseCreate, session: DatabaseSession, service: Estimator
) -> House:
    """Store a house. Requires the API key."""
    service.require_known_zipcode(body.zipcode)
    house = House(**body.model_dump())
    session.add(house)
    session.commit()
    session.refresh(house)
    return house


@router.get("/{house_id}", response_model=HouseOut)
def get_house(house_id: int, session: DatabaseSession) -> House:
    """Fetch one house."""
    return _get_or_404(session, house_id)


@router.put("/{house_id}", response_model=HouseOut, dependencies=[WriteAccess])
def update_house(
    house_id: int, body: HouseUpdate, session: DatabaseSession, service: Estimator
) -> House:
    """Replace a house's facts. Requires the API key."""
    service.require_known_zipcode(body.zipcode)
    house = _get_or_404(session, house_id)
    for field, value in body.model_dump().items():
        setattr(house, field, value)
    session.commit()
    session.refresh(house)
    return house


@router.delete(
    "/{house_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[WriteAccess]
)
def delete_house(house_id: int, session: DatabaseSession) -> Response:
    """Delete a house. Requires the API key."""
    session.delete(_get_or_404(session, house_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{house_id}/estimate", response_model=EstimateResponse)
def estimate_stored_house(
    house_id: int, session: DatabaseSession, service: Estimator
) -> EstimateResponse:
    """Estimate a stored house's price (assumes it is not on the waterfront)."""
    house = _get_or_404(session, house_id)
    answers = {
        "bedrooms": house.bedrooms,
        "bathrooms": house.bathrooms,
        "sqft_living": house.sqft_living,
        "grade": house.grade,
        "zipcode": house.zipcode,
        "waterfront": 0,
    }
    return build_response(service.estimate(answers), service)
