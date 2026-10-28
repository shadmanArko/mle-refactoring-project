"""Database tables and engine creation (nothing connects at import time)."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool


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
    # A frozen or unreachable database must produce a fast 503, never a hang.
    # A pooled connection would be re-used on an already-open socket, where no connect
    # timeout applies, so each request opens its own (NullPool) and the 2-second
    # connect timeout always does. It also suits Lambda, which freezes idle
    # connections. Behind RDS Proxy, or at real traffic, switch to a pool.
    return create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 2})
