"""FastAPI CRUD app backed by Postgres."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import Base, engine, get_db

app = FastAPI(
    title="Bonus Solution API",
    description="Reference FastAPI CRUD app for the optional project stretch goal.",
    version="1.0.0",
)

Base.metadata.create_all(bind=engine)

DatabaseSession = Annotated[Session, Depends(get_db)]


def get_house_or_404(db: Session, house_id: int) -> models.House:
    """Return one house or raise the public not-found response."""
    house = db.get(models.House, house_id)
    if house is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"House {house_id} was not found.",
        )
    return house


@app.get("/", tags=["health"])
def index() -> dict[str, str]:
    """Return a lightweight service status response."""
    return {"status": "ok"}


@app.get("/houses", response_model=list[schemas.HouseOut])
def get_all_houses(db: DatabaseSession) -> list[models.House]:
    """Return all persisted houses ordered by identifier."""
    statement = select(models.House).order_by(models.House.id)
    return list(db.scalars(statement))


@app.get("/houses/{house_id}", response_model=schemas.HouseOut)
def get_house(house_id: int, db: DatabaseSession) -> models.House:
    """Return one persisted house by identifier."""
    return get_house_or_404(db, house_id)


@app.post(
    "/houses", response_model=schemas.HouseOut, status_code=status.HTTP_201_CREATED
)
def create_house(request: schemas.HouseCreate, db: DatabaseSession) -> models.House:
    """Validate and persist a new house."""
    new_house = models.House(**request.model_dump())
    db.add(new_house)
    db.commit()
    db.refresh(new_house)
    return new_house


@app.put("/houses/{house_id}", response_model=schemas.HouseOut)
def update_house(
    house_id: int, request: schemas.HouseUpdate, db: DatabaseSession
) -> models.House:
    """Replace the editable fields of one house."""
    existing_house = get_house_or_404(db, house_id)

    for field, value in request.model_dump().items():
        setattr(existing_house, field, value)

    db.commit()
    db.refresh(existing_house)
    return existing_house


@app.delete("/houses/{house_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_house(house_id: int, db: DatabaseSession) -> Response:
    """Delete one house or return 404 when it does not exist."""
    house = get_house_or_404(db, house_id)

    db.delete(house)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
