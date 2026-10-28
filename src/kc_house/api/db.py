"""Database tables and engine creation (nothing connects at import time)."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class shared by the app's SQLAlchemy models."""


class House(Base):
    """A house a user wants to keep, described by five facts."""

    __tablename__ = "houses"

    id: Mapped[int] = mapped_column(primary_key=True)
    bedrooms: Mapped[int]
    bathrooms: Mapped[float]
    sqft_living: Mapped[int]
    grade: Mapped[int]
    zipcode: Mapped[int] = mapped_column(index=True)


def make_engine(url: str) -> Engine:
    """Create an engine that checks connections before use (Lambda freezes them)."""
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)
