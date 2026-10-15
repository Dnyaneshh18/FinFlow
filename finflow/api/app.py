"""FastAPI application factory.

Creates and configures the FastAPI application with:
- API routes
- CORS middleware
- Exception handling
- OpenAPI documentation
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from finflow.api.routes.routes import router
from finflow.core.config import get_settings
from finflow.core.logging import setup_logging
from finflow.db.session import create_all_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.is_sqlite:
        create_all_tables()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    setup_logging()

    app = FastAPI(
        title="FinFlow — Financial Data ETL & Reconciliation Platform",
        description=(
            "A financial data engineering platform that processes synthetic "
            "transaction records, validates data quality, and reconciles "
            "transactions between independent sources."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS for dashboard
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler — never expose internal stack traces
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal error occurred. Check server logs for details.",
                "type": type(exc).__name__,
            },
        )

    # Include routes
    app.include_router(router)

    return app


app = create_app()
