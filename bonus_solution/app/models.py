"""SQLAlchemy models for the FastAPI bonus solution."""

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class House(Base):
    __tablename__ = "houses"

    id: Mapped[int] = mapped_column(primary_key=True)
    bedrooms: Mapped[int] = mapped_column(Integer)
    bathrooms: Mapped[float] = mapped_column(Float)
    sqft_living: Mapped[int] = mapped_column(Integer)
    grade: Mapped[int] = mapped_column(Integer)
    zipcode: Mapped[str] = mapped_column(String(10))
