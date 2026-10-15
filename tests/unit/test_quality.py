"""Unit tests for data quality validation rules."""

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from finflow.quality.rules import (
    check_date_not_future,
    check_external_reference_present,
    check_required_account_id,
    check_required_transaction_id,
    check_valid_amount,
    check_valid_currency,
    check_valid_date,
    check_valid_transaction_type,
)
from finflow.quality.validation import (
    detect_duplicates,
    is_record_valid,
    validate_record,
)


class TestRequiredTransactionId:
    def test_valid_id(self):
        r = check_required_transaction_id({"transaction_id": "TX-001"})
        assert r.passed is True

    def test_missing_id(self):
        r = check_required_transaction_id({"transaction_id": None})
        assert r.passed is False
        assert r.severity == "ERROR"

    def test_empty_id(self):
        r = check_required_transaction_id({"transaction_id": ""})
        assert r.passed is False

    def test_blank_id(self):
        r = check_required_transaction_id({"transaction_id": "   "})
        assert r.passed is False


class TestRequiredAccountId:
    def test_valid(self):
        r = check_required_account_id({"account_id": "ACC-001"})
        assert r.passed is True

    def test_missing(self):
        r = check_required_account_id({"account_id": None})
        assert r.passed is False
        assert r.severity == "ERROR"


class TestValidAmount:
    def test_valid_amount(self):
        r = check_valid_amount({"amount_decimal": Decimal("100.00"), "amount": "100.00"})
        assert r.passed is True

    def test_zero_amount(self):
        r = check_valid_amount({"amount_decimal": Decimal("0"), "amount": "0"})
        assert r.passed is True

    def test_none_amount(self):
        r = check_valid_amount({"amount_decimal": None, "amount": "abc"})
        assert r.passed is False
        assert r.severity == "ERROR"


class TestValidCurrency:
    def test_valid_usd(self):
        r = check_valid_currency({"currency_normalized": "USD"})
        assert r.passed is True

    def test_invalid_currency(self):
        r = check_valid_currency({"currency_normalized": "XYZ"})
        assert r.passed is False
        assert r.severity == "ERROR"

    def test_none_currency(self):
        r = check_valid_currency({"currency_normalized": None})
        assert r.passed is False


class TestValidDate:
    def test_valid_date(self):
        dt = datetime(2024, 1, 15, tzinfo=UTC)
        r = check_valid_date({"date_parsed": dt, "transaction_date": "2024-01-15"})
        assert r.passed is True

    def test_none_date(self):
        r = check_valid_date({"date_parsed": None, "transaction_date": "not-a-date"})
        assert r.passed is False
        assert r.severity == "ERROR"


class TestDateNotFuture:
    def test_past_date(self):
        dt = datetime(2024, 1, 1, tzinfo=UTC)
        r = check_date_not_future({"date_parsed": dt})
        assert r.passed is True

    def test_future_date(self):
        dt = datetime(2099, 12, 31, tzinfo=UTC)
        r = check_date_not_future({"date_parsed": dt})
        assert r.passed is False
        assert r.severity == "WARNING"

    def test_none_date_skipped(self):
        r = check_date_not_future({"date_parsed": None})
        assert r.passed is True  # Skip, already caught by VALID_DATE


class TestValidTransactionType:
    def test_valid_credit(self):
        r = check_valid_transaction_type({"type_normalized": "CREDIT"})
        assert r.passed is True

    def test_valid_debit(self):
        r = check_valid_transaction_type({"type_normalized": "DEBIT"})
        assert r.passed is True

    def test_invalid_type(self):
        r = check_valid_transaction_type({"type_normalized": "UNKNOWN"})
        assert r.passed is False

    def test_none_type(self):
        r = check_valid_transaction_type({"type_normalized": None})
        assert r.passed is False


class TestExternalReference:
    def test_present(self):
        r = check_external_reference_present({"external_reference": "REF-001"})
        assert r.passed is True

    def test_missing(self):
        r = check_external_reference_present({"external_reference": None})
        assert r.passed is False
        assert r.severity == "WARNING"  # Not an error


class TestDuplicateDetection:
    def test_no_duplicates(self):
        df = pd.DataFrame(
            {
                "transaction_id": ["TX-1", "TX-2", "TX-3"],
                "source_system": ["SOURCE_A", "SOURCE_A", "SOURCE_A"],
            }
        )
        dups = detect_duplicates(df)
        assert len(dups) == 0

    def test_detects_duplicates(self):
        df = pd.DataFrame(
            {
                "transaction_id": ["TX-1", "TX-2", "TX-1"],
                "source_system": ["SOURCE_A", "SOURCE_A", "SOURCE_A"],
            }
        )
        dups = detect_duplicates(df)
        assert len(dups) == 1
        assert 2 in dups  # Third row is the dup

    def test_same_id_different_source_not_duplicate(self):
        df = pd.DataFrame(
            {
                "transaction_id": ["TX-1", "TX-1"],
                "source_system": ["SOURCE_A", "SOURCE_B"],
            }
        )
        dups = detect_duplicates(df)
        assert len(dups) == 0


class TestValidateRecord:
    def test_valid_record(self):
        row = {
            "transaction_id": "TX-001",
            "account_id": "ACC-001",
            "amount_decimal": Decimal("100.00"),
            "amount": "100.00",
            "currency_normalized": "USD",
            "date_parsed": datetime(2024, 1, 1, tzinfo=UTC),
            "transaction_date": "2024-01-01",
            "type_normalized": "CREDIT",
            "external_reference": "REF-001",
        }
        results = validate_record(row)
        assert all(r.passed for r in results)
        assert is_record_valid(results)

    def test_invalid_record_rejected(self):
        row = {
            "transaction_id": None,
            "account_id": "ACC-001",
            "amount_decimal": Decimal("100.00"),
            "amount": "100.00",
            "currency_normalized": "USD",
            "date_parsed": datetime(2024, 1, 1, tzinfo=UTC),
            "transaction_date": "2024-01-01",
            "type_normalized": "CREDIT",
            "external_reference": "REF-001",
        }
        results = validate_record(row)
        assert not is_record_valid(results)
