"""Data quality validation rules.

Each rule is a function that takes a DataFrame row and returns a
QualityCheckResult. Rules are configurable by severity.

Business Rules:
- transaction_id: Required, non-empty
- external_reference: Optional but expected
- account_id: Required, non-empty
- amount: Required, must be a valid Decimal, zero is allowed
- currency: Required, must be a valid ISO 4217 code from the allowed set
- transaction_date: Required, must be a valid parseable date, not in the future
- transaction_type: Required, must be from the allowed set
- Duplicates: Detected by (transaction_id, source_system) combination
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from finflow.transformations.normalize import VALID_CURRENCIES, VALID_TRANSACTION_TYPES


@dataclass
class QualityCheckResult:
    """Result of a single quality check on a single record."""

    rule_id: str
    passed: bool
    severity: str  # ERROR, WARNING, INFO
    field_name: str | None = None
    field_value: str | None = None
    failure_reason: str | None = None


def check_required_transaction_id(row: dict) -> QualityCheckResult:
    """Transaction ID must be present and non-empty."""
    value = row.get("transaction_id")
    passed = value is not None and not pd.isna(value) and str(value).strip() != ""
    return QualityCheckResult(
        rule_id="REQUIRED_TRANSACTION_ID",
        passed=passed,
        severity="ERROR",
        field_name="transaction_id",
        field_value=str(value)[:256] if value and not pd.isna(value) else None,
        failure_reason=None if passed else "Transaction ID is required and must not be empty",
    )


def check_required_account_id(row: dict) -> QualityCheckResult:
    """Account ID must be present and non-empty."""
    value = row.get("account_id")
    passed = value is not None and not pd.isna(value) and str(value).strip() != ""
    return QualityCheckResult(
        rule_id="REQUIRED_ACCOUNT_ID",
        passed=passed,
        severity="ERROR",
        field_name="account_id",
        field_value=str(value)[:256] if value and not pd.isna(value) else None,
        failure_reason=None if passed else "Account ID is required and must not be empty",
    )


def check_valid_amount(row: dict) -> QualityCheckResult:
    """Amount must be a valid Decimal. Zero is allowed."""
    value = row.get("amount_decimal")
    raw_value = row.get("amount")
    passed = value is not None and not pd.isna(value) and isinstance(value, Decimal)
    return QualityCheckResult(
        rule_id="VALID_AMOUNT",
        passed=passed,
        severity="ERROR",
        field_name="amount",
        field_value=str(raw_value)[:256] if raw_value and not pd.isna(raw_value) else None,
        failure_reason=None if passed else f"Amount '{raw_value}' is not a valid decimal number",
    )


def check_valid_currency(row: dict) -> QualityCheckResult:
    """Currency must be a valid code from the allowed set."""
    value = row.get("currency_normalized")
    passed = value is not None and not pd.isna(value) and value in VALID_CURRENCIES
    return QualityCheckResult(
        rule_id="VALID_CURRENCY",
        passed=passed,
        severity="ERROR",
        field_name="currency",
        field_value=str(value)[:256] if value and not pd.isna(value) else None,
        failure_reason=None
        if passed
        else (f"Currency '{value}' is not valid. Allowed: {sorted(VALID_CURRENCIES)}"),
    )


def check_valid_date(row: dict) -> QualityCheckResult:
    """Transaction date must be a valid, parseable date."""
    value = row.get("date_parsed")
    raw_value = row.get("transaction_date")
    passed = (
        value is not None
        and not pd.isna(value)
        and isinstance(value, datetime)
    )
    return QualityCheckResult(
        rule_id="VALID_DATE",
        passed=passed,
        severity="ERROR",
        field_name="transaction_date",
        field_value=str(raw_value)[:256] if raw_value and not pd.isna(raw_value) else None,
        failure_reason=None
        if passed
        else (
            f"Date '{raw_value}' could not be parsed. "
            f"Expected formats: YYYY-MM-DD HH:MM:SS or DD/MM/YYYY HH:MM"
        ),
    )


def check_date_not_future(row: dict) -> QualityCheckResult:
    """Transaction date should not be in the future."""
    value = row.get("date_parsed")
    if value is None or pd.isna(value) or not isinstance(value, datetime):
        return QualityCheckResult(
            rule_id="DATE_NOT_FUTURE",
            passed=True,  # Skip if date is already invalid
            severity="WARNING",
            field_name="transaction_date",
        )
    now = datetime.now(UTC)
    passed = value <= now
    return QualityCheckResult(
        rule_id="DATE_NOT_FUTURE",
        passed=passed,
        severity="WARNING",
        field_name="transaction_date",
        field_value=str(value.isoformat())[:256],
        failure_reason=None if passed else "Transaction date is in the future",
    )


def check_valid_transaction_type(row: dict) -> QualityCheckResult:
    """Transaction type must be from the allowed set."""
    value = row.get("type_normalized")
    passed = value is not None and not pd.isna(value) and value in VALID_TRANSACTION_TYPES
    return QualityCheckResult(
        rule_id="VALID_TRANSACTION_TYPE",
        passed=passed,
        severity="ERROR",
        field_name="transaction_type",
        field_value=str(value)[:256] if value else None,
        failure_reason=None
        if passed
        else (
            f"Transaction type '{value}' is not valid. Allowed: {sorted(VALID_TRANSACTION_TYPES)}"
        ),
    )


def check_external_reference_present(row: dict) -> QualityCheckResult:
    """External reference should be present (warning only)."""
    value = row.get("external_reference")
    passed = value is not None and str(value).strip() != ""
    return QualityCheckResult(
        rule_id="EXTERNAL_REFERENCE_PRESENT",
        passed=passed,
        severity="WARNING",
        field_name="external_reference",
        field_value=str(value)[:256] if value else None,
        failure_reason=None
        if passed
        else "External reference is missing (reconciliation may be affected)",
    )


# All validation rules in order of execution
ALL_RULES = [
    check_required_transaction_id,
    check_required_account_id,
    check_valid_amount,
    check_valid_currency,
    check_valid_date,
    check_date_not_future,
    check_valid_transaction_type,
    check_external_reference_present,
]

# Rules that cause a record to be rejected if they fail
REJECTION_RULES = {
    "REQUIRED_TRANSACTION_ID",
    "REQUIRED_ACCOUNT_ID",
    "VALID_AMOUNT",
    "VALID_CURRENCY",
    "VALID_DATE",
    "VALID_TRANSACTION_TYPE",
}
