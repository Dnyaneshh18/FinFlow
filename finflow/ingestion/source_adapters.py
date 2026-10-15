"""Source adapters for normalizing different source file formats.

Each source system has different column names and formats.
Adapters map source-specific columns to a common internal schema.
"""

from __future__ import annotations

import pandas as pd

from finflow.core.logging import get_logger
from finflow.ingestion.readers import IngestionError

logger = get_logger(__name__)

# Common internal column names
INTERNAL_COLUMNS = [
    "transaction_id",
    "external_reference",
    "account_id",
    "transaction_date",
    "currency",
    "amount",
    "transaction_type",
    "description",
]

# Source A mapping (already close to internal names)
SOURCE_A_MAPPING = {
    "transaction_id": "transaction_id",
    "external_reference": "external_reference",
    "account_id": "account_id",
    "transaction_date": "transaction_date",
    "currency": "currency",
    "amount": "amount",
    "transaction_type": "transaction_type",
    "description": "description",
}

# Source B mapping (different column names)
SOURCE_B_MAPPING = {
    "txn_id": "transaction_id",
    "ext_ref": "external_reference",
    "acct_id": "account_id",
    "txn_date": "transaction_date",
    "ccy": "currency",
    "amt": "amount",
    "txn_type": "transaction_type",
    "desc": "description",
}


def detect_source_system(df: pd.DataFrame) -> str:
    """Detect which source system a DataFrame came from based on column names."""
    columns = set(col.strip().lower() for col in df.columns)

    source_b_cols = {"txn_id", "ext_ref", "acct_id", "txn_date", "ccy", "amt", "txn_type"}
    source_a_cols = {"transaction_id", "external_reference", "account_id", "transaction_date"}

    if source_b_cols.issubset(columns):
        return "SOURCE_B"
    elif source_a_cols.issubset(columns):
        return "SOURCE_A"
    else:
        raise IngestionError(
            f"Cannot detect source system. Columns found: {list(df.columns)}. "
            f"Expected Source A columns {list(SOURCE_A_MAPPING.keys())} "
            f"or Source B columns {list(SOURCE_B_MAPPING.keys())}."
        )


def apply_column_mapping(df: pd.DataFrame, source_system: str) -> pd.DataFrame:
    """Apply column mapping to normalize source-specific columns to internal names."""
    if source_system == "SOURCE_A":
        mapping = SOURCE_A_MAPPING
    elif source_system == "SOURCE_B":
        mapping = SOURCE_B_MAPPING
    else:
        raise IngestionError(f"Unknown source system: {source_system}")

    # Normalize input column names (strip whitespace, lowercase)
    df.columns = [col.strip().lower() for col in df.columns]

    # Verify required columns exist
    missing = set(mapping.keys()) - set(df.columns)
    if missing:
        raise IngestionError(f"Missing required columns for {source_system}: {missing}")

    # Rename columns
    df = df.rename(columns=mapping)

    # Keep only mapped columns
    df = df[INTERNAL_COLUMNS]

    logger.info(
        "columns_mapped",
        source=source_system,
        columns=INTERNAL_COLUMNS,
    )
    return df
