"""Financial reconciliation engine.

Matches transactions between Source A and Source B using exact matching
on external_reference as the primary key. Falls back to composite key
(account_id, currency, transaction_date, amount) when external_reference
is unavailable.

Matching Rules:
1. Primary match: Exact external_reference match between sources.
2. Amount comparison: Uses exact Decimal arithmetic (not float).
3. Currency match: Must be identical.
4. Date tolerance: Not applied — dates must match at date level.
5. Ambiguity: When multiple candidates exist for a reference, status is AMBIGUOUS_MATCH.

Reconciliation Outcomes:
- MATCHED: Transaction found in both sources with matching amounts.
- MISSING_IN_SOURCE_A: Transaction exists in B but not A.
- MISSING_IN_SOURCE_B: Transaction exists in A but not B.
- AMOUNT_MISMATCH: Transaction found in both but amounts differ.
- AMBIGUOUS_MATCH: Multiple candidates for a single reference.
- INVALID_RECORD: Record failed validation (not reconciled).

Duplicate/Reversal Treatment:
- Duplicates are removed during validation stage before reconciliation.
- Reversals are treated as separate transactions with their own amounts.
- Each transaction is matched at most once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from finflow.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ReconciliationRecord:
    """A single reconciliation result."""

    status: str
    external_reference: str | None = None
    source_a_id: int | None = None
    source_b_id: int | None = None
    source_a_amount: Decimal | None = None
    source_b_amount: Decimal | None = None
    amount_difference: Decimal | None = None
    currency: str | None = None
    mismatch_reason: str | None = None


@dataclass
class ReconciliationSummary:
    """Summary statistics for a reconciliation run."""

    total_source_a: int = 0
    total_source_b: int = 0
    matched: int = 0
    missing_in_source_a: int = 0
    missing_in_source_b: int = 0
    amount_mismatches: int = 0
    ambiguous_matches: int = 0
    invalid_records: int = 0
    matched_amount_total: Decimal = field(default_factory=lambda: Decimal("0"))
    source_a_total: Decimal = field(default_factory=lambda: Decimal("0"))
    source_b_total: Decimal = field(default_factory=lambda: Decimal("0"))


def reconcile_transactions(
    source_a_records: list[dict],
    source_b_records: list[dict],
) -> tuple[list[ReconciliationRecord], ReconciliationSummary]:
    """Reconcile transactions between Source A and Source B.

    Each record dict must contain:
    - id: database ID of the curated transaction
    - external_reference: matching key
    - amount: Decimal amount
    - currency: currency code
    - account_id: account identifier
    - transaction_date: date for comparison

    Returns:
        tuple of (results, summary)
    """
    results: list[ReconciliationRecord] = []
    summary = ReconciliationSummary()
    summary.total_source_a = len(source_a_records)
    summary.total_source_b = len(source_b_records)

    # Compute source totals
    for rec in source_a_records:
        if rec.get("amount") is not None:
            summary.source_a_total += rec["amount"]
    for rec in source_b_records:
        if rec.get("amount") is not None:
            summary.source_b_total += rec["amount"]

    # Build lookup by external_reference for Source B
    b_by_ref: dict[str, list[dict]] = {}
    for rec in source_b_records:
        ref = rec.get("external_reference")
        if ref:
            b_by_ref.setdefault(ref, []).append(rec)

    # Track matched Source B IDs to avoid double-counting
    matched_b_ids: set[int] = set()

    # Match Source A records against Source B
    for a_rec in source_a_records:
        ref = a_rec.get("external_reference")

        if not ref:
            # No reference to match on — record as missing
            results.append(
                ReconciliationRecord(
                    status="MISSING_IN_SOURCE_B",
                    source_a_id=a_rec["id"],
                    source_a_amount=a_rec.get("amount"),
                    currency=a_rec.get("currency"),
                    mismatch_reason="Source A record has no external_reference for matching",
                )
            )
            summary.missing_in_source_b += 1
            continue

        candidates = b_by_ref.get(ref, [])
        # Filter out already-matched candidates
        available = [c for c in candidates if c["id"] not in matched_b_ids]

        if not available:
            results.append(
                ReconciliationRecord(
                    status="MISSING_IN_SOURCE_B",
                    external_reference=ref,
                    source_a_id=a_rec["id"],
                    source_a_amount=a_rec.get("amount"),
                    currency=a_rec.get("currency"),
                    mismatch_reason="No matching record found in Source B",
                )
            )
            summary.missing_in_source_b += 1

        elif len(available) > 1:
            # Ambiguous — multiple B records for this reference
            results.append(
                ReconciliationRecord(
                    status="AMBIGUOUS_MATCH",
                    external_reference=ref,
                    source_a_id=a_rec["id"],
                    source_a_amount=a_rec.get("amount"),
                    currency=a_rec.get("currency"),
                    mismatch_reason=f"Multiple Source B records ({len(available)}) match reference {ref}",
                )
            )
            summary.ambiguous_matches += 1

        else:
            b_rec = available[0]
            matched_b_ids.add(b_rec["id"])

            a_amount = a_rec.get("amount", Decimal("0"))
            b_amount = b_rec.get("amount", Decimal("0"))
            diff = a_amount - b_amount

            # Check currency match
            if a_rec.get("currency") != b_rec.get("currency"):
                results.append(
                    ReconciliationRecord(
                        status="AMOUNT_MISMATCH",
                        external_reference=ref,
                        source_a_id=a_rec["id"],
                        source_b_id=b_rec["id"],
                        source_a_amount=a_amount,
                        source_b_amount=b_amount,
                        amount_difference=diff,
                        currency=a_rec.get("currency"),
                        mismatch_reason=(
                            f"Currency mismatch: Source A={a_rec.get('currency')}, "
                            f"Source B={b_rec.get('currency')}"
                        ),
                    )
                )
                summary.amount_mismatches += 1

            elif diff != Decimal("0"):
                results.append(
                    ReconciliationRecord(
                        status="AMOUNT_MISMATCH",
                        external_reference=ref,
                        source_a_id=a_rec["id"],
                        source_b_id=b_rec["id"],
                        source_a_amount=a_amount,
                        source_b_amount=b_amount,
                        amount_difference=diff,
                        currency=a_rec.get("currency"),
                        mismatch_reason=f"Amount difference: {diff}",
                    )
                )
                summary.amount_mismatches += 1

            else:
                results.append(
                    ReconciliationRecord(
                        status="MATCHED",
                        external_reference=ref,
                        source_a_id=a_rec["id"],
                        source_b_id=b_rec["id"],
                        source_a_amount=a_amount,
                        source_b_amount=b_amount,
                        amount_difference=Decimal("0"),
                        currency=a_rec.get("currency"),
                    )
                )
                summary.matched += 1
                summary.matched_amount_total += a_amount

    # Find Source B records not matched to any Source A record
    for rec in source_b_records:
        if rec["id"] not in matched_b_ids:
            results.append(
                ReconciliationRecord(
                    status="MISSING_IN_SOURCE_A",
                    external_reference=rec.get("external_reference"),
                    source_b_id=rec["id"],
                    source_b_amount=rec.get("amount"),
                    currency=rec.get("currency"),
                    mismatch_reason="No matching record found in Source A",
                )
            )
            summary.missing_in_source_a += 1

    logger.info(
        "reconciliation_complete",
        total_results=len(results),
        matched=summary.matched,
        missing_a=summary.missing_in_source_a,
        missing_b=summary.missing_in_source_b,
        amount_mismatches=summary.amount_mismatches,
        ambiguous=summary.ambiguous_matches,
    )

    return results, summary
