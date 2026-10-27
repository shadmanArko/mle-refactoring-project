"""Database configuration for the FastAPI bonus solution."""

import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DB_CONN")

if DATABASE_URL is None:
    raise ValueError("DB_CONN environment variable is required")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    """Base class shared by the app's SQLAlchemy models."""


def get_db() -> Generator[Session]:
    """Yield one database session for a request, then close it."""
    with SessionLocal() as session:
        yield session
