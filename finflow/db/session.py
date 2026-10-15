"""Database session management.

Provides engine creation, session factory, and dependency injection
for FastAPI endpoints.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from finflow.core.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {}
        if settings.is_sqlite:
            connect_args["check_same_thread"] = False

        _engine = create_engine(
            settings.database_url,
            echo=settings.app_debug,
            pool_pre_ping=not settings.is_sqlite,
            connect_args=connect_args,
        )

        # Enable WAL mode and foreign keys for SQLite
        if settings.is_sqlite:

            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return _engine


def get_session_factory() -> sessionmaker:
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables():
    """Create all tables from models. Used for SQLite/testing only.
    In production, use Alembic migrations.
    """
    import finflow.db.models  # noqa: F401 - ensure models are imported
    from finflow.db.base import Base

    Base.metadata.create_all(bind=get_engine())


def reset_engine():
    """Reset engine and session factory. Used in tests."""
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
