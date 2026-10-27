"""Pydantic schemas for the FastAPI bonus solution."""

from pydantic import BaseModel, ConfigDict, Field


class HouseBase(BaseModel):
    """Fields shared by house creation, update, and response contracts."""

    bedrooms: int = Field(ge=0, le=20)
    bathrooms: float = Field(ge=0, le=20)
    sqft_living: int = Field(ge=100)
    grade: int = Field(ge=1, le=13)
    zipcode: str = Field(min_length=5, max_length=10)


class HouseCreate(HouseBase):
    """Request body used to create a house."""


class HouseUpdate(HouseBase):
    """Request body used to replace a house."""


class HouseOut(HouseBase):
    """Response body returned for persisted houses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
