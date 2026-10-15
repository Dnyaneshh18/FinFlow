"""Synthetic financial data generator.

Generates realistic but entirely fictional transaction data from two sources:
- Source A: Internal Finance System
- Source B: Bank Transaction Statement

Uses a configurable random seed for reproducibility.
Includes controlled test cases for validation and reconciliation testing.
"""

from __future__ import annotations

import csv
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from finflow.core.config import get_settings
from finflow.core.logging import get_logger

logger = get_logger(__name__)

# Valid values
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CAD"]
TRANSACTION_TYPES_A = ["CREDIT", "DEBIT", "TRANSFER", "REVERSAL", "FEE"]
TRANSACTION_TYPES_B = ["credit", "debit", "transfer", "reversal", "fee"]  # Different casing
ACCOUNTS = [f"ACC-{i:04d}" for i in range(1, 21)]
DESCRIPTIONS = [
    "Wire transfer payment",
    "Invoice settlement",
    "Payroll processing",
    "Vendor payment",
    "Client refund",
    "Interest accrual",
    "Service fee",
    "Dividend payment",
    "Tax payment",
    "Insurance premium",
    "Loan repayment",
    "Equipment purchase",
    "Utility payment",
    "Subscription renewal",
    "Commission payout",
]

# Source A columns
SOURCE_A_COLUMNS = [
    "transaction_id",
    "external_reference",
    "account_id",
    "transaction_date",
    "currency",
    "amount",
    "transaction_type",
    "description",
]

# Source B columns (different naming convention)
SOURCE_B_COLUMNS = [
    "txn_id",
    "ext_ref",
    "acct_id",
    "txn_date",
    "ccy",
    "amt",
    "txn_type",
    "desc",
]


def generate_sample_data(
    num_transactions: int | None = None,
    seed: int | None = None,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Generate paired source files with controlled test cases.

    Returns paths to (source_a_file, source_b_file).
    """
    settings = get_settings()
    num_tx = num_transactions or settings.data_num_transactions
    rng_seed = seed or settings.data_seed
    out_dir = output_dir or settings.sample_data_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(rng_seed)

    # Generate base transactions that exist in both sources
    base_count = int(num_tx * 0.7)  # 70% matching
    transactions = []

    base_date = datetime(2024, 1, 1, tzinfo=UTC)

    for i in range(base_count):
        ext_ref = f"REF-{uuid.UUID(int=rng.getrandbits(128)).hex[:12].upper()}"
        tx_id_a = f"FIN-{i + 1:06d}"
        tx_id_b = f"BNK-{i + 1:06d}"
        account = rng.choice(ACCOUNTS)
        currency = rng.choice(CURRENCIES)
        amount = Decimal(str(round(rng.uniform(10, 50000), 2)))
        tx_type = rng.choice(TRANSACTION_TYPES_A)
        desc = rng.choice(DESCRIPTIONS)
        tx_date = base_date + timedelta(
            days=rng.randint(0, 180),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )

        transactions.append(
            {
                "ext_ref": ext_ref,
                "tx_id_a": tx_id_a,
                "tx_id_b": tx_id_b,
                "account": account,
                "currency": currency,
                "amount": amount,
                "tx_type": tx_type,
                "desc": desc,
                "tx_date": tx_date,
                "match_type": "MATCHED",
            }
        )

    # --- Controlled test cases ---

    # Amount mismatches (5%)
    mismatch_count = int(num_tx * 0.05)
    for i in range(mismatch_count):
        ext_ref = f"REF-MISMATCH-{i + 1:04d}"
        amount_a = Decimal(str(round(rng.uniform(100, 10000), 2)))
        amount_b = amount_a + Decimal(str(round(rng.uniform(0.01, 50), 2)))
        tx_date = base_date + timedelta(days=rng.randint(0, 180))
        transactions.append(
            {
                "ext_ref": ext_ref,
                "tx_id_a": f"FIN-MM-{i + 1:04d}",
                "tx_id_b": f"BNK-MM-{i + 1:04d}",
                "account": rng.choice(ACCOUNTS),
                "currency": rng.choice(CURRENCIES),
                "amount_a": amount_a,
                "amount_b": amount_b,
                "tx_type": rng.choice(TRANSACTION_TYPES_A),
                "desc": f"Amount mismatch test case {i + 1}",
                "tx_date": tx_date,
                "match_type": "AMOUNT_MISMATCH",
            }
        )

    # Missing in Source B (5%)
    missing_b_count = int(num_tx * 0.05)
    source_a_only = []
    for i in range(missing_b_count):
        tx_date = base_date + timedelta(days=rng.randint(0, 180))
        source_a_only.append(
            {
                "ext_ref": f"REF-ONLYA-{i + 1:04d}",
                "tx_id_a": f"FIN-OA-{i + 1:04d}",
                "account": rng.choice(ACCOUNTS),
                "currency": rng.choice(CURRENCIES),
                "amount": Decimal(str(round(rng.uniform(10, 5000), 2))),
                "tx_type": rng.choice(TRANSACTION_TYPES_A),
                "desc": f"Only in Source A {i + 1}",
                "tx_date": tx_date,
            }
        )

    # Missing in Source A (5%)
    missing_a_count = int(num_tx * 0.05)
    source_b_only = []
    for i in range(missing_a_count):
        tx_date = base_date + timedelta(days=rng.randint(0, 180))
        source_b_only.append(
            {
                "ext_ref": f"REF-ONLYB-{i + 1:04d}",
                "tx_id_b": f"BNK-OB-{i + 1:04d}",
                "account": rng.choice(ACCOUNTS),
                "currency": rng.choice(CURRENCIES),
                "amount": Decimal(str(round(rng.uniform(10, 5000), 2))),
                "tx_type": rng.choice(TRANSACTION_TYPES_A),
                "desc": f"Only in Source B {i + 1}",
                "tx_date": tx_date,
            }
        )

    # Duplicates in Source A (2%)
    dup_count = max(2, int(num_tx * 0.02))

    # Invalid records (3%)
    invalid_count = int(num_tx * 0.03)

    # Zero amount transaction
    zero_tx = {
        "ext_ref": "REF-ZERO-0001",
        "tx_id_a": "FIN-ZERO-0001",
        "tx_id_b": "BNK-ZERO-0001",
        "account": "ACC-0001",
        "currency": "USD",
        "amount": Decimal("0.00"),
        "tx_type": "ADJUSTMENT",
        "desc": "Zero amount adjustment",
        "tx_date": base_date + timedelta(days=90),
        "match_type": "MATCHED",
    }
    transactions.append(zero_tx)

    # --- Write Source A ---
    source_a_path = out_dir / "source_a_transactions.csv"
    with open(source_a_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(SOURCE_A_COLUMNS)

        for tx in transactions:
            amount = tx.get("amount_a", tx.get("amount"))
            writer.writerow(
                [
                    tx["tx_id_a"],
                    tx["ext_ref"],
                    tx["account"],
                    tx["tx_date"].strftime("%Y-%m-%d %H:%M:%S"),
                    tx["currency"],
                    str(amount),
                    tx["tx_type"],
                    tx["desc"],
                ]
            )

        for tx in source_a_only:
            writer.writerow(
                [
                    tx["tx_id_a"],
                    tx["ext_ref"],
                    tx["account"],
                    tx["tx_date"].strftime("%Y-%m-%d %H:%M:%S"),
                    tx["currency"],
                    str(tx["amount"]),
                    tx["tx_type"],
                    tx["desc"],
                ]
            )

        # Duplicates: repeat first few matching transactions
        for i in range(dup_count):
            tx = transactions[i]
            amount = tx.get("amount_a", tx.get("amount"))
            writer.writerow(
                [
                    tx["tx_id_a"],
                    tx["ext_ref"],
                    tx["account"],
                    tx["tx_date"].strftime("%Y-%m-%d %H:%M:%S"),
                    tx["currency"],
                    str(amount),
                    tx["tx_type"],
                    tx["desc"],
                ]
            )

        # Invalid records
        for i in range(invalid_count):
            if i % 5 == 0:
                # Missing transaction_id
                writer.writerow(
                    [
                        "",
                        f"REF-INV-{i + 1:04d}",
                        rng.choice(ACCOUNTS),
                        "2024-03-15 10:00:00",
                        "USD",
                        "100.00",
                        "CREDIT",
                        "Missing ID test",
                    ]
                )
            elif i % 5 == 1:
                # Invalid date
                writer.writerow(
                    [
                        f"FIN-INV-{i + 1:04d}",
                        f"REF-INV-{i + 1:04d}",
                        rng.choice(ACCOUNTS),
                        "not-a-date",
                        "USD",
                        "200.00",
                        "DEBIT",
                        "Invalid date test",
                    ]
                )
            elif i % 5 == 2:
                # Invalid amount
                writer.writerow(
                    [
                        f"FIN-INV-{i + 1:04d}",
                        f"REF-INV-{i + 1:04d}",
                        rng.choice(ACCOUNTS),
                        "2024-04-01 12:00:00",
                        "USD",
                        "abc",
                        "CREDIT",
                        "Invalid amount test",
                    ]
                )
            elif i % 5 == 3:
                # Invalid currency
                writer.writerow(
                    [
                        f"FIN-INV-{i + 1:04d}",
                        f"REF-INV-{i + 1:04d}",
                        rng.choice(ACCOUNTS),
                        "2024-04-15 14:00:00",
                        "XYZ",
                        "500.00",
                        "CREDIT",
                        "Invalid currency test",
                    ]
                )
            else:
                # Missing mandatory field (account_id)
                writer.writerow(
                    [
                        f"FIN-INV-{i + 1:04d}",
                        f"REF-INV-{i + 1:04d}",
                        "",
                        "2024-05-01 09:00:00",
                        "EUR",
                        "300.00",
                        "TRANSFER",
                        "Missing account test",
                    ]
                )

    # --- Write Source B ---
    source_b_path = out_dir / "source_b_transactions.csv"
    with open(source_b_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(SOURCE_B_COLUMNS)

        for tx in transactions:
            amount = tx.get("amount_b", tx.get("amount"))
            # Source B uses different date format
            date_str = tx["tx_date"].strftime("%d/%m/%Y %H:%M")
            tx_type_b = tx["tx_type"].lower()
            writer.writerow(
                [
                    tx["tx_id_b"],
                    tx["ext_ref"],
                    tx["account"],
                    date_str,
                    tx["currency"],
                    str(amount),
                    tx_type_b,
                    tx["desc"],
                ]
            )

        for tx in source_b_only:
            date_str = tx["tx_date"].strftime("%d/%m/%Y %H:%M")
            writer.writerow(
                [
                    tx["tx_id_b"],
                    tx["ext_ref"],
                    tx["account"],
                    date_str,
                    tx["currency"],
                    str(tx["amount"]),
                    tx["tx_type"].lower(),
                    tx["desc"],
                ]
            )

    logger.info(
        "sample_data_generated",
        source_a=str(source_a_path),
        source_b=str(source_b_path),
        total_matched=base_count,
        mismatches=mismatch_count,
        missing_in_b=missing_b_count,
        missing_in_a=missing_a_count,
        duplicates_in_a=dup_count,
        invalid_in_a=invalid_count,
    )

    return source_a_path, source_b_path


if __name__ == "__main__":
    a, b = generate_sample_data()
    print(f"Generated: {a}, {b}")
