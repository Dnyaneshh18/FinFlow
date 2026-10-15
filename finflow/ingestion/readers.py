"""File readers for CSV source data ingestion.

Handles file validation, hashing, and reading with robust error handling.
Supports multiple encodings and validates file structure before processing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from finflow.core.logging import get_logger

logger = get_logger(__name__)

# Maximum file size: 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".csv"}


class IngestionError(Exception):
    """Raised when file ingestion fails."""

    pass


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA-256 hash of a file for deduplication."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_file(filepath: Path) -> None:
    """Validate file exists, has allowed extension, and is within size limits.

    Raises IngestionError on validation failure.
    """
    if not filepath.exists():
        raise IngestionError(f"File not found: {filepath.name}")

    if filepath.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise IngestionError(
            f"Unsupported file extension: {filepath.suffix}. Allowed: {ALLOWED_EXTENSIONS}"
        )

    file_size = filepath.stat().st_size
    if file_size == 0:
        raise IngestionError(f"File is empty: {filepath.name}")

    if file_size > MAX_FILE_SIZE:
        raise IngestionError(
            f"File too large: {file_size / (1024 * 1024):.1f} MB. "
            f"Maximum: {MAX_FILE_SIZE / (1024 * 1024):.0f} MB"
        )

    # Validate it's readable as text
    try:
        with open(filepath, encoding="utf-8") as f:
            f.read(1024)
    except UnicodeDecodeError:
        try:
            with open(filepath, encoding="latin-1") as f:
                f.read(1024)
        except Exception as err:
            raise IngestionError(f"File encoding not supported: {filepath.name}") from err


def validate_path_safe(filepath: Path, allowed_dir: Path) -> Path:
    """Prevent path traversal attacks by ensuring the file is within allowed directory."""
    resolved = filepath.resolve()
    allowed = allowed_dir.resolve()
    if not str(resolved).startswith(str(allowed)):
        raise IngestionError("Path traversal detected — file must be within allowed directory")
    return resolved


def read_csv_file(filepath: Path) -> pd.DataFrame:
    """Read a CSV file into a DataFrame with robust error handling.

    Returns a DataFrame with all columns as strings to preserve original values.
    """
    validate_file(filepath)

    try:
        # First try UTF-8
        df = pd.read_csv(filepath, dtype=str, encoding="utf-8", keep_default_na=False)
    except UnicodeDecodeError:
        # Fallback to latin-1
        logger.warning("utf8_decode_failed", file=filepath.name, fallback="latin-1")
        df = pd.read_csv(filepath, dtype=str, encoding="latin-1", keep_default_na=False)
    except pd.errors.EmptyDataError as err:
        raise IngestionError(f"File contains no data: {filepath.name}") from err
    except pd.errors.ParserError as err:
        raise IngestionError(f"CSV parsing error in {filepath.name}: {err}") from err

    if df.empty:
        raise IngestionError(f"File contains headers but no data rows: {filepath.name}")

    if len(df.columns) < 3:
        raise IngestionError(
            f"File has too few columns ({len(df.columns)}). "
            f"Expected at least 3 columns for transaction data."
        )

    logger.info("csv_file_read", file=filepath.name, rows=len(df), columns=list(df.columns))
    return df
