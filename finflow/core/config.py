"""FinFlow application configuration using Pydantic Settings.

All configuration is read from environment variables or .env file.
No secrets are hardcoded.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = Field(
        default="sqlite:///./finflow.db",
        description="Database connection URL. Use postgresql+psycopg://... for PostgreSQL.",
    )

    # Application
    app_env: str = Field(default="development")
    app_debug: bool = Field(default=False)
    app_secret_key: str = Field(default="dev-only-change-in-production")

    # API
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    # Dashboard
    dashboard_port: int = Field(default=8501)

    # Data Generation
    data_seed: int = Field(default=42)
    data_num_transactions: int = Field(default=500)

    # File Upload
    max_upload_size_mb: int = Field(default=50)
    allowed_extensions: str = Field(default=".csv")

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")

    # Paths
    project_root: Path = Field(default_factory=lambda: Path(__file__).parent.parent.parent)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def sample_data_dir(self) -> Path:
        return self.data_dir / "sample"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.database_url


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
