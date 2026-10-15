"""Unit tests for the ingestion module."""

import pandas as pd
import pytest

from finflow.ingestion.readers import (
    IngestionError,
    compute_file_hash,
    read_csv_file,
    validate_file,
)
from finflow.ingestion.source_adapters import (
    apply_column_mapping,
    detect_source_system,
)


class TestFileHash:
    def test_consistent_hash(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        hash1 = compute_file_hash(f)
        hash2 = compute_file_hash(f)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "test1.csv"
        f2 = tmp_path / "test2.csv"
        f1.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        f2.write_text("a,b,c\n4,5,6\n", encoding="utf-8")
        assert compute_file_hash(f1) != compute_file_hash(f2)


class TestValidateFile:
    def test_nonexistent_file(self, tmp_path):
        with pytest.raises(IngestionError, match="not found"):
            validate_file(tmp_path / "nope.csv")

    def test_wrong_extension(self, tmp_path):
        f = tmp_path / "test.xlsx"
        f.write_text("data")
        with pytest.raises(IngestionError, match="Unsupported"):
            validate_file(f)

    def test_empty_file(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("")
        with pytest.raises(IngestionError, match="empty"):
            validate_file(f)

    def test_valid_file(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        validate_file(f)  # Should not raise


class TestReadCsvFile:
    def test_reads_valid_csv(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text(
            "transaction_id,external_reference,account_id,transaction_date,"
            "currency,amount,transaction_type,description\n"
            "TX-1,REF-1,ACC-1,2024-01-01,USD,100.00,CREDIT,Test\n",
            encoding="utf-8",
        )
        df = read_csv_file(f)
        assert len(df) == 1
        assert "transaction_id" in df.columns

    def test_all_columns_are_strings(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("a,b,c,d\n1,2.5,true,text\n", encoding="utf-8")
        df = read_csv_file(f)
        for col in df.columns:
            assert str(df[col].dtype) in ("object", "string", "str") or df[col].dtype == object
            assert isinstance(df[col].iloc[0], str)

    def test_headers_only_raises(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("a,b,c,d\n", encoding="utf-8")
        with pytest.raises(IngestionError, match="no data rows"):
            read_csv_file(f)


class TestSourceDetection:
    def test_detects_source_a(self):
        df = pd.DataFrame(
            columns=[
                "transaction_id",
                "external_reference",
                "account_id",
                "transaction_date",
                "currency",
                "amount",
                "transaction_type",
                "description",
            ]
        )
        assert detect_source_system(df) == "SOURCE_A"

    def test_detects_source_b(self):
        df = pd.DataFrame(
            columns=[
                "txn_id",
                "ext_ref",
                "acct_id",
                "txn_date",
                "ccy",
                "amt",
                "txn_type",
                "desc",
            ]
        )
        assert detect_source_system(df) == "SOURCE_B"

    def test_unknown_source_raises(self):
        df = pd.DataFrame(columns=["col1", "col2", "col3"])
        with pytest.raises(IngestionError, match="Cannot detect"):
            detect_source_system(df)


class TestColumnMapping:
    def test_source_a_mapping(self):
        df = pd.DataFrame(
            {
                "transaction_id": ["TX-1"],
                "external_reference": ["REF-1"],
                "account_id": ["ACC-1"],
                "transaction_date": ["2024-01-01"],
                "currency": ["USD"],
                "amount": ["100"],
                "transaction_type": ["CREDIT"],
                "description": ["Test"],
            }
        )
        mapped = apply_column_mapping(df, "SOURCE_A")
        assert list(mapped.columns) == [
            "transaction_id",
            "external_reference",
            "account_id",
            "transaction_date",
            "currency",
            "amount",
            "transaction_type",
            "description",
        ]

    def test_source_b_mapping(self):
        df = pd.DataFrame(
            {
                "txn_id": ["TX-1"],
                "ext_ref": ["REF-1"],
                "acct_id": ["ACC-1"],
                "txn_date": ["01/01/2024"],
                "ccy": ["USD"],
                "amt": ["100"],
                "txn_type": ["credit"],
                "desc": ["Test"],
            }
        )
        mapped = apply_column_mapping(df, "SOURCE_B")
        assert "transaction_id" in mapped.columns
        assert "txn_id" not in mapped.columns
