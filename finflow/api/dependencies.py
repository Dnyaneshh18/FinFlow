"""FastAPI dependencies for dependency injection."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from finflow.db.session import get_db


def get_database() -> Generator[Session, None, None]:
    """Yield a database session for route handlers."""
    yield from get_db()
