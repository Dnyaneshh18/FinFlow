"""Integration tests for the full ETL pipeline and database operations.

These tests use a real database (SQLite for CI, PostgreSQL for full integration).
They verify end-to-end pipeline execution, idempotency, and data persistence.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Override DATABASE_URL before importing anything that reads settings
os.environ["DATABASE_URL"] = "sqlite:///./test_finflow.db"

import contextlib

from sqlalchemy import select

from finflow.db.base import Base
from finflow.db.models import (
    CuratedTransaction,
    QualityResult,
    RawTransaction,
    ReconciliationResult,
)
from finflow.db.session import get_engine, get_session_factory, reset_engine
from finflow.pipelines.orchestrator import run_pipeline


@pytest.fixture(autouse=True)
def clean_db():
    """Create a fresh database for each test."""
    # Reset engine to pick up test URL
    reset_engine()
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    reset_engine()
    # Clean up test db file
    if os.path.exists("test_finflow.db"):
        with contextlib.suppress(PermissionError):
            os.remove("test_finflow.db")


@pytest.fixture
def sample_files(tmp_path) -> tuple[Path, Path]:
    """Create minimal test CSV files."""
    source_a = tmp_path / "source_a.csv"
    source_a.write_text(
        "transaction_id,external_reference,account_id,transaction_date,"
        "currency,amount,transaction_type,description\n"
        "FIN-001,REF-001,ACC-0001,2024-01-15 10:00:00,USD,1000.00,CREDIT,Wire transfer\n"
        "FIN-002,REF-002,ACC-0002,2024-02-20 14:30:00,EUR,500.50,DEBIT,Invoice payment\n"
        "FIN-003,REF-003,ACC-0001,2024-03-10 09:15:00,USD,250.00,TRANSFER,Internal transfer\n",
        encoding="utf-8",
    )

    source_b = tmp_path / "source_b.csv"
    source_b.write_text(
        "txn_id,ext_ref,acct_id,txn_date,ccy,amt,txn_type,desc\n"
        "BNK-001,REF-001,ACC-0001,15/01/2024 10:00,USD,1000.00,credit,Wire transfer\n"
        "BNK-002,REF-002,ACC-0002,20/02/2024 14:30,EUR,500.50,debit,Invoice payment\n"
        "BNK-004,REF-004,ACC-0003,05/04/2024 16:00,GBP,750.00,credit,New payment\n",
        encoding="utf-8",
    )

    return source_a, source_b


class TestPipelineEndToEnd:
    def test_full_pipeline_execution(self, sample_files):
        """Run complete pipeline and verify all stages complete."""
        source_a, source_b = sample_files
        SessionLocal = get_session_factory()
        db = SessionLocal()

        try:
            run = run_pipeline(db, [source_a, source_b])

            assert run.status in ("SUCCEEDED", "PARTIALLY_SUCCEEDED")
            assert run.records_input == 6  # 3 + 3
            assert run.records_accepted > 0
            assert run.records_loaded > 0
            assert run.run_id.startswith("RUN-")
            assert run.duration_seconds is not None

            # Verify raw transactions stored
            raw_count = db.execute(select(func.count()).select_from(RawTransaction)).scalar()
            assert raw_count == 6

            # Verify curated transactions
            curated_count = db.execute(
                select(func.count()).select_from(CuratedTransaction)
            ).scalar()
            assert curated_count > 0

            # Verify quality results
            quality_count = db.execute(select(func.count()).select_from(QualityResult)).scalar()
            assert quality_count > 0

            # Verify reconciliation results
            recon_count = db.execute(
                select(func.count()).select_from(ReconciliationResult)
            ).scalar()
            assert recon_count > 0

        finally:
            db.close()

    def test_idempotent_rerun(self, sample_files):
        """Running the same files twice should not duplicate data."""
        source_a, source_b = sample_files
        SessionLocal = get_session_factory()
        db = SessionLocal()

        try:
            run1 = run_pipeline(db, [source_a, source_b])
            assert run1.status in ("SUCCEEDED", "PARTIALLY_SUCCEEDED")
            curated_after_run1 = db.execute(
                select(func.count()).select_from(CuratedTransaction)
            ).scalar()

            # Run again with same files
            run2 = run_pipeline(db, [source_a, source_b])
            assert run2.status in ("SUCCEEDED", "PARTIALLY_SUCCEEDED")
            curated_after_run2 = db.execute(
                select(func.count()).select_from(CuratedTransaction)
            ).scalar()

            # Same files should be skipped (file hash dedup)
            assert curated_after_run2 == curated_after_run1

        finally:
            db.close()

    def test_reconciliation_outcomes(self, sample_files):
        """Verify reconciliation produces expected match/mismatch outcomes."""
        source_a, source_b = sample_files
        SessionLocal = get_session_factory()
        db = SessionLocal()

        try:
            run = run_pipeline(db, [source_a, source_b])

            results = (
                db.execute(
                    select(ReconciliationResult).where(
                        ReconciliationResult.pipeline_run_id == run.id
                    )
                )
                .scalars()
                .all()
            )

            statuses = [r.status for r in results]
            # REF-001 and REF-002 should match
            assert "MATCHED" in statuses
            # REF-003 only in A, REF-004 only in B
            assert "MISSING_IN_SOURCE_B" in statuses
            assert "MISSING_IN_SOURCE_A" in statuses

        finally:
            db.close()

    def test_pipeline_with_invalid_data(self, tmp_path):
        """Pipeline handles invalid records without crashing."""
        source_a = tmp_path / "source_a.csv"
        source_a.write_text(
            "transaction_id,external_reference,account_id,transaction_date,"
            "currency,amount,transaction_type,description\n"
            ",REF-BAD,ACC-001,not-a-date,XYZ,abc,UNKNOWN,Bad record\n"
            "FIN-OK,REF-OK,ACC-002,2024-01-01 00:00:00,USD,100.00,CREDIT,Good record\n",
            encoding="utf-8",
        )

        SessionLocal = get_session_factory()
        db = SessionLocal()

        try:
            run = run_pipeline(db, [source_a])
            assert run.status in ("PARTIALLY_SUCCEEDED", "SUCCEEDED")
            assert run.records_rejected >= 1
            assert run.records_accepted >= 1

        finally:
            db.close()

    def test_failed_pipeline_status(self, tmp_path):
        """A deliberate file error produces FAILED status."""
        bad_file = tmp_path / "nonexistent.csv"
        SessionLocal = get_session_factory()
        db = SessionLocal()

        try:
            run = run_pipeline(db, [bad_file])
            assert run.status == "FAILED"
            assert run.error_message is not None

        finally:
            db.close()


# Need this import for func.count()
from sqlalchemy import func


class TestAPIIntegration:
    """Integration tests for FastAPI endpoints."""

    def test_health_endpoint(self):
        from fastapi.testclient import TestClient

        from finflow.api.app import create_app

        app = create_app()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"

    def test_pipeline_runs_empty(self):
        from fastapi.testclient import TestClient

        from finflow.api.app import create_app

        app = create_app()
        client = TestClient(app)
        response = client.get("/api/v1/pipeline-runs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_pipeline_run_not_found(self):
        from fastapi.testclient import TestClient

        from finflow.api.app import create_app

        app = create_app()
        client = TestClient(app)
        response = client.get("/api/v1/pipeline-runs/NONEXISTENT")
        assert response.status_code == 404

    def test_transactions_pagination(self, sample_files):
        from fastapi.testclient import TestClient

        from finflow.api.app import create_app

        # Run pipeline first
        source_a, source_b = sample_files
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            run_pipeline(db, [source_a, source_b])
        finally:
            db.close()

        app = create_app()
        client = TestClient(app)
        response = client.get("/api/v1/transactions?page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2

    def test_quality_summary(self, sample_files):
        from fastapi.testclient import TestClient

        from finflow.api.app import create_app

        source_a, source_b = sample_files
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            run_pipeline(db, [source_a, source_b])
        finally:
            db.close()

        app = create_app()
        client = TestClient(app)
        response = client.get("/api/v1/quality/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_checks" in data
        assert data["total_checks"] > 0

    def test_reconciliation_summary(self, sample_files):
        from fastapi.testclient import TestClient

        from finflow.api.app import create_app

        source_a, source_b = sample_files
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            run_pipeline(db, [source_a, source_b])
        finally:
            db.close()

        app = create_app()
        client = TestClient(app)
        response = client.get("/api/v1/reconciliation/summary")
        assert response.status_code == 200
        data = response.json()
        assert "matched" in data
