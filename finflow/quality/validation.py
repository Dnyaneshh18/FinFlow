"""Data quality validation engine.

Runs all configured rules against each record and produces
structured validation results. Separates valid from rejected records.

Policy:
- A record is REJECTED if any ERROR-severity rule fails.
- A record with WARNING-severity failures is ACCEPTED with warnings.
- Duplicate detection uses (transaction_id, source_system) as business key.
"""

from __future__ import annotations

import pandas as pd

from finflow.core.logging import get_logger
from finflow.quality.rules import (
    ALL_RULES,
    REJECTION_RULES,
    QualityCheckResult,
)

logger = get_logger(__name__)


def validate_record(row: dict) -> list[QualityCheckResult]:
    """Run all validation rules against a single record."""
    results = []
    for rule_fn in ALL_RULES:
        result = rule_fn(row)
        results.append(result)
    return results


def is_record_valid(results: list[QualityCheckResult]) -> bool:
    """Check if a record passes all rejection rules."""
    return all(r.passed or r.rule_id not in REJECTION_RULES for r in results)


def detect_duplicates(df: pd.DataFrame) -> set[int]:
    """Detect duplicate records by (transaction_id, source_system).

    Returns set of row indices that are duplicates (keeps first occurrence).
    """
    if "transaction_id" not in df.columns or "source_system" not in df.columns:
        return set()

    # Create mask for non-null transaction_ids
    has_id = df["transaction_id"].notna() & (df["transaction_id"] != "")
    valid_df = df[has_id]

    # Find duplicates keeping first
    dup_mask = valid_df.duplicated(subset=["transaction_id", "source_system"], keep="first")
    duplicate_indices = set(valid_df[dup_mask].index)

    if duplicate_indices:
        logger.warning(
            "duplicates_detected",
            count=len(duplicate_indices),
        )

    return duplicate_indices


def validate_dataframe(
    df: pd.DataFrame,
    pipeline_run_id: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """Validate all records in a DataFrame.

    Returns:
        tuple of (valid_df, rejected_df, quality_results)
        - valid_df: Records that passed all ERROR rules
        - rejected_df: Records that failed at least one ERROR rule
        - quality_results: List of dicts for each validation check
    """
    # Detect duplicates first
    duplicate_indices = detect_duplicates(df)

    valid_indices = []
    rejected_indices = []
    all_quality_results = []

    for idx, row in df.iterrows():
        row_dict = row.to_dict()
        results = validate_record(row_dict)

        # Add duplicate check result
        is_dup = idx in duplicate_indices
        dup_result = QualityCheckResult(
            rule_id="DUPLICATE_DETECTION",
            passed=not is_dup,
            severity="ERROR",
            field_name="transaction_id",
            field_value=str(row_dict.get("transaction_id", ""))[:256],
            failure_reason="Duplicate record detected (same transaction_id + source_system)"
            if is_dup
            else None,
        )
        results.append(dup_result)

        # Record all results
        for r in results:
            result_dict = {
                "pipeline_run_id": pipeline_run_id,
                "rule_id": r.rule_id,
                "source_system": row_dict.get("source_system"),
                "field_name": r.field_name,
                "field_value": r.field_value,
                "passed": r.passed,
                "severity": r.severity,
                "failure_reason": r.failure_reason,
                "row_index": idx,
            }
            all_quality_results.append(result_dict)

        # Determine if valid (check rejection rules + duplicates)
        record_valid = is_record_valid(results) and not is_dup
        if record_valid:
            valid_indices.append(idx)
        else:
            rejected_indices.append(idx)

    valid_df = df.loc[valid_indices].copy() if valid_indices else pd.DataFrame(columns=df.columns)
    rejected_df = (
        df.loc[rejected_indices].copy() if rejected_indices else pd.DataFrame(columns=df.columns)
    )

    logger.info(
        "validation_complete",
        total=len(df),
        valid=len(valid_df),
        rejected=len(rejected_df),
        quality_checks=len(all_quality_results),
    )

    return valid_df, rejected_df, all_quality_results
