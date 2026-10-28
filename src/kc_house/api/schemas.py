"""Request and response shapes. Lower bounds are the training data's minima
(1 bedroom, half a bathroom, 370 sq ft); upper bounds leave a little headroom."""

from pydantic import BaseModel, ConfigDict, Field


class HouseBase(BaseModel):
    """The five facts stored for a house."""

    bedrooms: int = Field(ge=1, le=12, examples=[3])
    bathrooms: float = Field(ge=0.5, le=8, multiple_of=0.25, examples=[2.0])
    sqft_living: int = Field(ge=370, le=14000, examples=[1800])
    grade: int = Field(ge=3, le=13, description="Build quality, 3 to 13.", examples=[7])
    zipcode: int = Field(ge=98001, le=98199, examples=[98103])


class HouseCreate(HouseBase):
    """Body used to create a house."""


class HouseUpdate(HouseBase):
    """Body used to replace a house."""


class HouseOut(HouseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class HouseList(BaseModel):
    items: list[HouseOut]
    total: int
    limit: int
    offset: int


class EstimateRequest(HouseBase):
    """The six answers behind an estimate."""

    waterfront: bool = False


class EstimateResponse(BaseModel):
    estimate: int = Field(description="Best guess, US dollars, rounded to $1,000.")
    low: int
    high: int
    coverage: float = Field(
        description="Share of past houses that landed in the range."
    )
    typical_error_pct: float
    model_version: str
    note: str
