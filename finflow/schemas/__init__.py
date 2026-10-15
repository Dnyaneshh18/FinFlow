"""Pydantic schemas for API request/response validation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pipeline Run
# ---------------------------------------------------------------------------
class PipelineRunBase(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    current_stage: str | None = None
    source_files: str | None = None
    records_input: int = 0
    records_processed: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    records_loaded: int = 0
    error_message: str | None = None
    duration_seconds: float | None = None

    model_config = {"from_attributes": True}


class PipelineRunSummary(BaseModel):
    """Compact run summary for list views."""

    run_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    records_input: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    duration_seconds: float | None = None

    model_config = {"from_attributes": True}


class PipelineRunCreate(BaseModel):
    """Request to trigger a pipeline run."""

    source_files: list[str] = Field(
        ..., min_length=1, description="List of source file paths to process"
    )


class PipelineRunResponse(PipelineRunBase):
    id: int


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------
class QualityIssue(BaseModel):
    id: int
    rule_id: str
    source_system: str | None = None
    field_name: str | None = None
    field_value: str | None = None
    passed: bool
    severity: str
    failure_reason: str | None = None
    checked_at: datetime

    model_config = {"from_attributes": True}


class QualitySummary(BaseModel):
    total_checks: int
    passed: int
    failed: int
    warnings: int
    error_rate: float
    top_failing_rules: list[dict]


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------
class ReconciliationItem(BaseModel):
    id: int
    status: str
    external_reference: str | None = None
    source_a_amount: Decimal | None = None
    source_b_amount: Decimal | None = None
    amount_difference: Decimal | None = None
    currency: str | None = None
    mismatch_reason: str | None = None
    matched_at: datetime

    model_config = {"from_attributes": True}


class ReconciliationSummary(BaseModel):
    total_source_a: int
    total_source_b: int
    matched: int
    missing_in_source_a: int
    missing_in_source_b: int
    amount_mismatches: int
    ambiguous_matches: int
    invalid_records: int
    match_rate: float
    matched_amount_total: Decimal
    source_a_total: Decimal
    source_b_total: Decimal
    total_difference: Decimal


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
class TransactionItem(BaseModel):
    id: int
    transaction_id: str
    external_reference: str | None = None
    account_id: str
    transaction_date: datetime
    currency: str
    amount: Decimal
    transaction_type: str
    source_system: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""

    items: list
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    database: str
    version: str = "0.1.0"
