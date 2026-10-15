"""API routes for pipeline runs, quality, reconciliation, and transactions.

All routes use Pydantic schemas for validation and return consistent
HTTP status codes. Pagination is enforced with a max page size of 100.
"""

from __future__ import annotations

import math
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finflow.api.dependencies import get_database
from finflow.core.config import get_settings
from finflow.db.models import (
    CuratedTransaction,
    PipelineRun,
    QualityResult,
    ReconciliationResult,
)
from finflow.schemas import (
    HealthResponse,
    PaginatedResponse,
    PipelineRunCreate,
    PipelineRunResponse,
    PipelineRunSummary,
    QualityIssue,
    QualitySummary,
    ReconciliationItem,
    ReconciliationSummary,
    TransactionItem,
)

router = APIRouter()

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def _paginate(query, page: int, page_size: int, db: Session):
    """Apply pagination to a query and return items + total count."""
    page_size = min(page_size, MAX_PAGE_SIZE)
    page = max(page, 1)

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = db.execute(count_q).scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    items = db.execute(query.offset(offset).limit(page_size)).scalars().all()
    total_pages = math.ceil(total / page_size) if page_size > 0 else 0

    return items, total, page, page_size, total_pages


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@router.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check(db: Session = Depends(get_database)):
    """Check application and database health."""
    try:
        db.execute(select(func.count()).select_from(PipelineRun))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    return HealthResponse(status="ok", database=db_status)


# ---------------------------------------------------------------------------
# Pipeline Runs
# ---------------------------------------------------------------------------
@router.get(
    "/api/v1/pipeline-runs",
    response_model=PaginatedResponse,
    tags=["Pipeline"],
)
def list_pipeline_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status: str | None = Query(None),
    db: Session = Depends(get_database),
):
    """List pipeline runs with optional status filter."""
    query = select(PipelineRun).order_by(PipelineRun.started_at.desc())
    if status:
        query = query.where(PipelineRun.status == status.upper())

    items, total, pg, ps, tp = _paginate(query, page, page_size, db)
    return PaginatedResponse(
        items=[PipelineRunSummary.model_validate(i) for i in items],
        total=total,
        page=pg,
        page_size=ps,
        total_pages=tp,
    )


@router.get(
    "/api/v1/pipeline-runs/{run_id}",
    response_model=PipelineRunResponse,
    tags=["Pipeline"],
)
def get_pipeline_run(run_id: str, db: Session = Depends(get_database)):
    """Get details of a specific pipeline run."""
    run = db.execute(select(PipelineRun).where(PipelineRun.run_id == run_id)).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")
    return PipelineRunResponse.model_validate(run)


@router.post(
    "/api/v1/pipeline-runs",
    response_model=PipelineRunResponse,
    status_code=201,
    tags=["Pipeline"],
)
def trigger_pipeline_run(
    body: PipelineRunCreate,
    db: Session = Depends(get_database),
):
    """Trigger a new pipeline run.

    Note: In production, this endpoint should require authentication.
    In this demo, it accepts source file paths from the data/sample directory.
    """
    from finflow.pipelines.orchestrator import run_pipeline

    settings = get_settings()

    # Validate and resolve file paths (prevent path traversal)
    resolved_files = []
    for f in body.source_files:
        filepath = Path(f)
        if not filepath.is_absolute():
            filepath = settings.sample_data_dir / filepath
        filepath = filepath.resolve()

        # Security: ensure file is within project
        project_root = settings.project_root.resolve()
        if not str(filepath).startswith(str(project_root)):
            raise HTTPException(
                status_code=400, detail="File path must be within the project directory"
            )
        if not filepath.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {filepath.name}")
        resolved_files.append(filepath)

    run = run_pipeline(db, resolved_files)
    return PipelineRunResponse.model_validate(run)


# ---------------------------------------------------------------------------
# Data Quality
# ---------------------------------------------------------------------------
@router.get("/api/v1/quality/summary", response_model=QualitySummary, tags=["Quality"])
def get_quality_summary(
    run_id: str | None = Query(None),
    db: Session = Depends(get_database),
):
    """Get data quality summary, optionally filtered by run."""
    base_q = select(QualityResult)
    if run_id:
        run = db.execute(
            select(PipelineRun).where(PipelineRun.run_id == run_id)
        ).scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        base_q = base_q.where(QualityResult.pipeline_run_id == run.id)

    total = db.execute(select(func.count()).select_from(base_q.subquery())).scalar() or 0
    passed = (
        db.execute(
            select(func.count()).select_from(
                base_q.where(QualityResult.passed.is_(True)).subquery()
            )
        ).scalar()
        or 0
    )
    failed_errors = (
        db.execute(
            select(func.count()).select_from(
                base_q.where(
                    QualityResult.passed.is_(False), QualityResult.severity == "ERROR"
                ).subquery()
            )
        ).scalar()
        or 0
    )
    warnings = (
        db.execute(
            select(func.count()).select_from(
                base_q.where(
                    QualityResult.passed.is_(False), QualityResult.severity == "WARNING"
                ).subquery()
            )
        ).scalar()
        or 0
    )

    # Top failing rules
    top_rules_q = select(
        QualityResult.rule_id,
        func.count().label("count"),
    ).where(QualityResult.passed.is_(False))
    if run_id and run:
        top_rules_q = top_rules_q.where(QualityResult.pipeline_run_id == run.id)
    top_rules_q = (
        top_rules_q.group_by(QualityResult.rule_id).order_by(func.count().desc()).limit(10)
    )

    top_rules = db.execute(top_rules_q).all()
    top_failing = [{"rule_id": r[0], "count": r[1]} for r in top_rules]

    return QualitySummary(
        total_checks=total,
        passed=passed,
        failed=failed_errors,
        warnings=warnings,
        error_rate=round(failed_errors / total * 100, 2) if total > 0 else 0,
        top_failing_rules=top_failing,
    )


@router.get("/api/v1/quality/issues", response_model=PaginatedResponse, tags=["Quality"])
def list_quality_issues(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    run_id: str | None = Query(None),
    severity: str | None = Query(None),
    rule_id: str | None = Query(None),
    db: Session = Depends(get_database),
):
    """List quality issues (failed checks) with filters."""
    query = select(QualityResult).where(QualityResult.passed.is_(False))
    if run_id:
        run = db.execute(
            select(PipelineRun).where(PipelineRun.run_id == run_id)
        ).scalar_one_or_none()
        if run:
            query = query.where(QualityResult.pipeline_run_id == run.id)
    if severity:
        query = query.where(QualityResult.severity == severity.upper())
    if rule_id:
        query = query.where(QualityResult.rule_id == rule_id)

    query = query.order_by(QualityResult.id.desc())
    items, total, pg, ps, tp = _paginate(query, page, page_size, db)
    return PaginatedResponse(
        items=[QualityIssue.model_validate(i) for i in items],
        total=total,
        page=pg,
        page_size=ps,
        total_pages=tp,
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------
@router.get(
    "/api/v1/reconciliation/summary",
    response_model=ReconciliationSummary,
    tags=["Reconciliation"],
)
def get_reconciliation_summary(
    run_id: str | None = Query(None),
    db: Session = Depends(get_database),
):
    """Get reconciliation summary statistics."""
    base_q = select(ReconciliationResult)
    if run_id:
        run = db.execute(
            select(PipelineRun).where(PipelineRun.run_id == run_id)
        ).scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        base_q = base_q.where(ReconciliationResult.pipeline_run_id == run.id)

    all_results = db.execute(base_q).scalars().all()

    # Compute source counts from curated transactions
    a_count_q = select(func.count(CuratedTransaction.id)).where(
        CuratedTransaction.source_system == "SOURCE_A"
    )
    b_count_q = select(func.count(CuratedTransaction.id)).where(
        CuratedTransaction.source_system == "SOURCE_B"
    )
    if run_id and run:
        a_count_q = a_count_q.where(CuratedTransaction.pipeline_run_id == run.id)
        b_count_q = b_count_q.where(CuratedTransaction.pipeline_run_id == run.id)

    total_a = db.execute(a_count_q).scalar() or 0
    total_b = db.execute(b_count_q).scalar() or 0

    counts = {
        "MATCHED": 0,
        "MISSING_IN_SOURCE_A": 0,
        "MISSING_IN_SOURCE_B": 0,
        "AMOUNT_MISMATCH": 0,
        "AMBIGUOUS_MATCH": 0,
        "INVALID_RECORD": 0,
    }
    matched_total = Decimal("0")
    a_total = Decimal("0")
    b_total = Decimal("0")

    for r in all_results:
        counts[r.status] = counts.get(r.status, 0) + 1
        if r.status == "MATCHED" and r.source_a_amount:
            matched_total += r.source_a_amount
        if r.source_a_amount:
            a_total += r.source_a_amount
        if r.source_b_amount:
            b_total += r.source_b_amount

    total_recon = sum(counts.values())
    match_rate = round(counts["MATCHED"] / total_recon * 100, 2) if total_recon > 0 else 0

    return ReconciliationSummary(
        total_source_a=total_a,
        total_source_b=total_b,
        matched=counts["MATCHED"],
        missing_in_source_a=counts["MISSING_IN_SOURCE_A"],
        missing_in_source_b=counts["MISSING_IN_SOURCE_B"],
        amount_mismatches=counts["AMOUNT_MISMATCH"],
        ambiguous_matches=counts["AMBIGUOUS_MATCH"],
        invalid_records=counts["INVALID_RECORD"],
        match_rate=match_rate,
        matched_amount_total=matched_total,
        source_a_total=a_total,
        source_b_total=b_total,
        total_difference=a_total - b_total,
    )


@router.get(
    "/api/v1/reconciliation/exceptions",
    response_model=PaginatedResponse,
    tags=["Reconciliation"],
)
def list_reconciliation_exceptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    run_id: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_database),
):
    """List reconciliation exceptions (non-matched records)."""
    query = select(ReconciliationResult).where(ReconciliationResult.status != "MATCHED")

    if run_id:
        run = db.execute(
            select(PipelineRun).where(PipelineRun.run_id == run_id)
        ).scalar_one_or_none()
        if run:
            query = query.where(ReconciliationResult.pipeline_run_id == run.id)
    if status:
        query = query.where(ReconciliationResult.status == status.upper())

    query = query.order_by(ReconciliationResult.id.desc())
    items, total, pg, ps, tp = _paginate(query, page, page_size, db)
    return PaginatedResponse(
        items=[ReconciliationItem.model_validate(i) for i in items],
        total=total,
        page=pg,
        page_size=ps,
        total_pages=tp,
    )


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
@router.get(
    "/api/v1/transactions",
    response_model=PaginatedResponse,
    tags=["Transactions"],
)
def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    source: str | None = Query(None),
    account_id: str | None = Query(None),
    currency: str | None = Query(None),
    transaction_type: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_database),
):
    """List curated transactions with filters."""
    query = select(CuratedTransaction).order_by(CuratedTransaction.transaction_date.desc())

    if source:
        query = query.where(CuratedTransaction.source_system == source.upper())
    if account_id:
        query = query.where(CuratedTransaction.account_id == account_id)
    if currency:
        query = query.where(CuratedTransaction.currency == currency.upper())
    if transaction_type:
        query = query.where(CuratedTransaction.transaction_type == transaction_type.upper())
    if date_from:
        query = query.where(CuratedTransaction.transaction_date >= date_from)
    if date_to:
        query = query.where(CuratedTransaction.transaction_date <= date_to)

    items, total, pg, ps, tp = _paginate(query, page, page_size, db)
    return PaginatedResponse(
        items=[TransactionItem.model_validate(i) for i in items],
        total=total,
        page=pg,
        page_size=ps,
        total_pages=tp,
    )
