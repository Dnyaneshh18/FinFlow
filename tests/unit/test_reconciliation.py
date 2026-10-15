"""Unit tests for the reconciliation engine."""

from decimal import Decimal

from finflow.reconciliation.matcher import reconcile_transactions


def _make_record(rec_id, ref, amount, currency="USD", account="ACC-001"):
    return {
        "id": rec_id,
        "external_reference": ref,
        "amount": Decimal(str(amount)),
        "currency": currency,
        "account_id": account,
        "transaction_date": "2024-01-15",
    }


class TestReconciliation:
    def test_perfect_match(self):
        a = [_make_record(1, "REF-001", 100.00)]
        b = [_make_record(2, "REF-001", 100.00)]
        results, summary = reconcile_transactions(a, b)

        assert summary.matched == 1
        assert summary.missing_in_source_a == 0
        assert summary.missing_in_source_b == 0
        assert results[0].status == "MATCHED"
        assert results[0].amount_difference == Decimal("0")

    def test_amount_mismatch(self):
        a = [_make_record(1, "REF-001", 100.00)]
        b = [_make_record(2, "REF-001", 105.50)]
        results, summary = reconcile_transactions(a, b)

        assert summary.amount_mismatches == 1
        assert results[0].status == "AMOUNT_MISMATCH"
        assert results[0].amount_difference == Decimal("-5.50")

    def test_missing_in_source_b(self):
        a = [_make_record(1, "REF-001", 100.00)]
        b = []
        results, summary = reconcile_transactions(a, b)

        assert summary.missing_in_source_b == 1
        assert results[0].status == "MISSING_IN_SOURCE_B"

    def test_missing_in_source_a(self):
        a = []
        b = [_make_record(2, "REF-001", 100.00)]
        results, summary = reconcile_transactions(a, b)

        assert summary.missing_in_source_a == 1
        assert results[0].status == "MISSING_IN_SOURCE_A"

    def test_ambiguous_match(self):
        a = [_make_record(1, "REF-001", 100.00)]
        b = [
            _make_record(2, "REF-001", 100.00),
            _make_record(3, "REF-001", 100.00),
        ]
        results, summary = reconcile_transactions(a, b)

        assert summary.ambiguous_matches == 1
        matched_statuses = [r.status for r in results]
        assert "AMBIGUOUS_MATCH" in matched_statuses

    def test_currency_mismatch(self):
        a = [_make_record(1, "REF-001", 100.00, currency="USD")]
        b = [_make_record(2, "REF-001", 100.00, currency="EUR")]
        results, summary = reconcile_transactions(a, b)

        assert summary.amount_mismatches == 1
        assert "Currency mismatch" in results[0].mismatch_reason

    def test_multiple_transactions(self):
        a = [
            _make_record(1, "REF-001", 100.00),
            _make_record(2, "REF-002", 200.00),
            _make_record(3, "REF-003", 300.00),
        ]
        b = [
            _make_record(4, "REF-001", 100.00),
            _make_record(5, "REF-002", 200.00),
        ]
        results, summary = reconcile_transactions(a, b)

        assert summary.matched == 2
        assert summary.missing_in_source_b == 1

    def test_no_double_counting(self):
        """Each Source B record matched at most once."""
        a = [
            _make_record(1, "REF-001", 100.00),
            _make_record(2, "REF-001", 100.00),
        ]
        b = [_make_record(3, "REF-001", 100.00)]
        results, summary = reconcile_transactions(a, b)

        # First A matches B, second A sees no available B
        assert summary.matched == 1
        assert summary.missing_in_source_b == 1

    def test_zero_amount_matched(self):
        a = [_make_record(1, "REF-ZERO", 0.00)]
        b = [_make_record(2, "REF-ZERO", 0.00)]
        results, summary = reconcile_transactions(a, b)

        assert summary.matched == 1
        assert results[0].amount_difference == Decimal("0")

    def test_exact_decimal_arithmetic(self):
        """Verify amounts use exact decimal, not float approximation."""
        a = [_make_record(1, "REF-001", "0.10")]
        b = [_make_record(2, "REF-001", "0.10")]
        results, summary = reconcile_transactions(a, b)

        assert summary.matched == 1
        assert results[0].amount_difference == Decimal("0")

    def test_summary_totals(self):
        a = [
            _make_record(1, "REF-001", 100.00),
            _make_record(2, "REF-002", 200.00),
        ]
        b = [
            _make_record(3, "REF-001", 100.00),
            _make_record(4, "REF-002", 200.00),
        ]
        results, summary = reconcile_transactions(a, b)

        assert summary.source_a_total == Decimal("300")
        assert summary.source_b_total == Decimal("300")
        assert summary.matched_amount_total == Decimal("300")

    def test_missing_external_reference(self):
        """Records without ext_ref are flagged as MISSING."""
        a = [_make_record(1, None, 100.00)]
        b = [_make_record(2, "REF-001", 100.00)]
        results, summary = reconcile_transactions(a, b)

        assert summary.missing_in_source_b == 1
        assert summary.missing_in_source_a == 1
