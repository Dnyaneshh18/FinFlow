"""Unit tests for the transformation/normalization module."""

from datetime import UTC
from decimal import Decimal

from finflow.transformations.normalize import (
    normalize_currency,
    normalize_text,
    normalize_transaction_type,
    parse_amount,
    parse_date,
)


class TestNormalizeText:
    def test_strips_whitespace(self):
        assert normalize_text("  hello  ") == "hello"

    def test_none_returns_none(self):
        assert normalize_text(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_text("") is None

    def test_blank_string_returns_none(self):
        assert normalize_text("   ") is None

    def test_preserves_content(self):
        assert normalize_text("Wire transfer") == "Wire transfer"


class TestParseAmount:
    def test_valid_positive(self):
        result = parse_amount("1234.56")
        assert result == Decimal("1234.5600")

    def test_valid_negative(self):
        result = parse_amount("-100.50")
        assert result == Decimal("-100.5000")

    def test_zero(self):
        result = parse_amount("0.00")
        assert result == Decimal("0.0000")

    def test_comma_thousands(self):
        result = parse_amount("1,234.56")
        assert result == Decimal("1234.5600")

    def test_parenthesized_negative(self):
        result = parse_amount("(500.00)")
        assert result == Decimal("-500.0000")

    def test_invalid_text(self):
        assert parse_amount("abc") is None

    def test_none_input(self):
        assert parse_amount(None) is None

    def test_empty_string(self):
        assert parse_amount("") is None

    def test_large_amount(self):
        result = parse_amount("99999999999999.9999")
        assert result is not None

    def test_precision_preserved(self):
        """Ensure exact decimal arithmetic — no float imprecision."""
        result = parse_amount("0.1")
        assert result == Decimal("0.1000")
        # This would fail with float: 0.1 + 0.2 != 0.3
        assert parse_amount("0.1") + parse_amount("0.2") == Decimal("0.3000")


class TestParseDate:
    def test_iso_format(self):
        result = parse_date("2024-01-15 10:30:00")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.tzinfo == UTC

    def test_european_format(self):
        result = parse_date("15/01/2024 10:30")
        assert result is not None
        assert result.day == 15
        assert result.month == 1

    def test_date_only(self):
        result = parse_date("2024-06-30")
        assert result is not None
        assert result.year == 2024

    def test_invalid_date(self):
        assert parse_date("not-a-date") is None

    def test_none_input(self):
        assert parse_date(None) is None

    def test_empty_string(self):
        assert parse_date("") is None

    def test_utc_timezone(self):
        """All parsed dates should be UTC."""
        result = parse_date("2024-03-15 12:00:00")
        assert result.tzinfo == UTC


class TestNormalizeCurrency:
    def test_uppercase(self):
        assert normalize_currency("usd") == "USD"

    def test_already_uppercase(self):
        assert normalize_currency("EUR") == "EUR"

    def test_strips_whitespace(self):
        assert normalize_currency("  gbp  ") == "GBP"

    def test_none_returns_none(self):
        assert normalize_currency(None) is None


class TestNormalizeTransactionType:
    def test_uppercase(self):
        assert normalize_transaction_type("credit") == "CREDIT"

    def test_already_uppercase(self):
        assert normalize_transaction_type("DEBIT") == "DEBIT"

    def test_none_returns_none(self):
        assert normalize_transaction_type(None) is None
