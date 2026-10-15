"""FinFlow database models.

Relational schema for the financial ETL & reconciliation platform.
Uses appropriate types for financial data: Numeric for amounts, proper
timestamps, and explicit constraints.

Schema entities:
- PipelineRun: Tracks each ETL pipeline execution
- IngestionBatch: Tracks each file ingestion within a run
- RawTransaction: Raw source records as ingested
- CuratedTransaction: Normalized, validated transactions
- QualityResult: Per-record validation outcomes
- ReconciliationResult: Per-record matching outcomes
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finflow.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Pipeline Run
# ---------------------------------------------------------------------------
class PipelineRun(Base):
    """Tracks a single ETL pipeline execution."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING",
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_files: Mapped[str | None] = mapped_column(Text, nullable=True)
    records_input: Mapped[int] = mapped_column(Integer, default=0)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_accepted: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    records_loaded: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Relationships
    batches: Mapped[list[IngestionBatch]] = relationship(back_populates="pipeline_run")
    quality_results: Mapped[list[QualityResult]] = relationship(back_populates="pipeline_run")
    reconciliation_results: Mapped[list[ReconciliationResult]] = relationship(
        back_populates="pipeline_run"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','PARTIALLY_SUCCEEDED')",
            name="ck_pipeline_run_status",
        ),
    )


# ---------------------------------------------------------------------------
# Ingestion Batch
# ---------------------------------------------------------------------------
class IngestionBatch(Base):
    """Tracks a single file ingestion within a pipeline run."""

    __tablename__ = "ingestion_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    pipeline_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED")

    # Relationships
    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="batches")
    raw_transactions: Mapped[list[RawTransaction]] = relationship(back_populates="batch")

    __table_args__ = (
        Index("ix_ingestion_batch_file_hash", "file_hash"),
        CheckConstraint(
            "source_system IN ('SOURCE_A','SOURCE_B')",
            name="ck_ingestion_batch_source",
        ),
    )


# ---------------------------------------------------------------------------
# Raw Transaction
# ---------------------------------------------------------------------------
class RawTransaction(Base):
    """Raw transaction record as ingested from source files.

    Preserves original field values for auditability.
    """

    __tablename__ = "raw_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ingestion_batches.id"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transaction_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    amount: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    batch: Mapped[IngestionBatch] = relationship(back_populates="raw_transactions")

    __table_args__ = (
        Index("ix_raw_tx_batch", "batch_id"),
        Index("ix_raw_tx_ext_ref", "external_reference"),
    )


# ---------------------------------------------------------------------------
# Curated Transaction
# ---------------------------------------------------------------------------
class CuratedTransaction(Base):
    """Normalized, validated transaction ready for analysis.

    Uses Numeric type for exact decimal arithmetic on financial amounts.
    """

    __tablename__ = "curated_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_transaction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("raw_transactions.id"), nullable=False
    )
    pipeline_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=False
    )
    transaction_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "transaction_id",
            "source_system",
            name="uq_curated_tx_id_source",
        ),
        Index("ix_curated_tx_ext_ref", "external_reference"),
        Index("ix_curated_tx_date", "transaction_date"),
        Index("ix_curated_tx_account", "account_id"),
        Index("ix_curated_tx_source", "source_system"),
        CheckConstraint(
            "source_system IN ('SOURCE_A','SOURCE_B')",
            name="ck_curated_tx_source",
        ),
        CheckConstraint(
            "currency IN ('USD','EUR','GBP','JPY','CAD','AUD','CHF')",
            name="ck_curated_tx_currency",
        ),
        CheckConstraint(
            "transaction_type IN ('CREDIT','DEBIT','TRANSFER','REVERSAL','FEE','ADJUSTMENT')",
            name="ck_curated_tx_type",
        ),
    )


# ---------------------------------------------------------------------------
# Quality Result
# ---------------------------------------------------------------------------
class QualityResult(Base):
    """Records the outcome of a data quality validation check."""

    __tablename__ = "quality_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=False
    )
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_transaction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("raw_transactions.id"), nullable=True
    )
    source_system: Mapped[str | None] = mapped_column(String(32), nullable=True)
    field_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    field_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    passed: Mapped[bool] = mapped_column(nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="ERROR")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="quality_results")

    __table_args__ = (
        Index("ix_quality_run", "pipeline_run_id"),
        Index("ix_quality_rule", "rule_id"),
        CheckConstraint(
            "severity IN ('ERROR','WARNING','INFO')",
            name="ck_quality_severity",
        ),
    )


# ---------------------------------------------------------------------------
# Reconciliation Result
# ---------------------------------------------------------------------------
class ReconciliationResult(Base):
    """Records the outcome of matching a transaction across sources."""

    __tablename__ = "reconciliation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=False
    )
    source_a_transaction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("curated_transactions.id"), nullable=True
    )
    source_b_transaction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("curated_transactions.id"), nullable=True
    )
    external_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_a_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    source_b_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount_difference: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    mismatch_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="reconciliation_results")

    __table_args__ = (
        Index("ix_recon_run", "pipeline_run_id"),
        Index("ix_recon_status", "status"),
        Index("ix_recon_ext_ref", "external_reference"),
        CheckConstraint(
            "status IN ('MATCHED','MISSING_IN_SOURCE_A','MISSING_IN_SOURCE_B',"
            "'AMOUNT_MISMATCH','AMBIGUOUS_MATCH','INVALID_RECORD')",
            name="ck_recon_status",
        ),
    )
