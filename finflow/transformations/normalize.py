"""Data transformation and normalization module.

Applies documented transformations to convert raw ingested data into
a standardized format. All transformations are independently testable.

Timezone Policy: All timestamps are normalized to UTC.
Amount Policy: All amounts are converted to Decimal with 4 decimal places.
Transaction Types: Normalized to uppercase.
Currency: Normalized to uppercase ISO 4217 codes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from finflow.core.logging import get_logger

logger = get_logger(__name__)

# Allowed values after normalization
VALID_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF"}
VALID_TRANSACTION_TYPES = {"CREDIT", "DEBIT", "TRANSFER", "REVERSAL", "FEE", "ADJUSTMENT"}

# Date format patterns to try
DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",  # 2024-01-15 10:30:00
    "%Y-%m-%dT%H:%M:%S",  # 2024-01-15T10:30:00
    "%Y-%m-%d",  # 2024-01-15
    "%d/%m/%Y %H:%M",  # 15/01/2024 10:30
    "%d/%m/%Y %H:%M:%S",  # 15/01/2024 10:30:00
    "%d/%m/%Y",  # 15/01/2024
    "%m/%d/%Y",  # 01/15/2024
    "%Y%m%d",  # 20240115
]


def normalize_text(value: str | None) -> str | None:
    """Normalize text by stripping whitespace. Returns None for empty/blank strings."""
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None


def normalize_currency(value: str | None) -> str | None:
    """Normalize currency code to uppercase 3-letter ISO 4217."""
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized if normalized else None


def normalize_transaction_type(value: str | None) -> str | None:
    """Normalize transaction type to uppercase."""
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized if normalized else None


def parse_amount(value: str | None) -> Decimal | None:
    """Parse amount string to exact Decimal.

    Returns None if the value cannot be parsed.
    Uses Decimal (not float) for exact financial arithmetic.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None

    # Remove common formatting characters
    value = value.replace(",", "").replace(" ", "")

    # Handle parenthesized negative amounts: (100.00) -> -100.00
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]

    try:
        return Decimal(value).quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError):
        return None


def parse_date(value: str | None) -> datetime | None:
    """Parse date string to UTC datetime.

    Tries multiple common formats. Returns None if none match.
    All dates are normalized to UTC timezone.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None

    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            # Ensure UTC timezone
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue

    return None


def normalize_dataframe(df: pd.DataFrame, source_system: str) -> pd.DataFrame:
    """Apply all normalizations to a DataFrame.

    The DataFrame should already have internal column names
    (applied by source_adapters).

    Adds columns:
    - amount_decimal: Decimal amount (None if parse fails)
    - date_parsed: datetime (None if parse fails)
    - currency_normalized: uppercase currency
    - type_normalized: uppercase transaction type
    - source_system: source identifier

    Does NOT silently drop rows — invalid values are kept as None
    for the quality validation stage to handle.
    """
    result = df.copy()

    # Normalize text fields
    result["transaction_id"] = result["transaction_id"].apply(normalize_text)
    result["external_reference"] = result["external_reference"].apply(normalize_text)
    result["account_id"] = result["account_id"].apply(normalize_text)
    result["description"] = result["description"].apply(normalize_text)

    # Parse and normalize amounts
    result["amount_decimal"] = result["amount"].apply(parse_amount)

    # Parse and normalize dates
    result["date_parsed"] = result["transaction_date"].apply(parse_date)

    # Normalize currency and type
    result["currency_normalized"] = result["currency"].apply(normalize_currency)
    result["type_normalized"] = result["transaction_type"].apply(normalize_transaction_type)

    # Add source system
    result["source_system"] = source_system

    # Add row numbers for tracking
    result["row_number"] = range(1, len(result) + 1)

    logger.info(
        "dataframe_normalized",
        source=source_system,
        rows=len(result),
        null_amounts=int(result["amount_decimal"].isna().sum()),
        null_dates=int(result["date_parsed"].isna().sum()),
    )

    return result
