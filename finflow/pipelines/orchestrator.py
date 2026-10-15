"""ETL Pipeline Orchestrator.

Coordinates the complete ETL pipeline:
1. EXTRACT: Read and validate source files
2. TRANSFORM: Normalize and standardize data
3. VALIDATE: Run quality checks, separate valid/rejected
4. LOAD: Persist raw, curated, and quality data to database
5. RECONCILE: Match Source A against Source B

Each run gets a unique run_id. The orchestrator handles:
- Stage tracking and status updates
- Error handling with safe rollbacks
- Idempotent re-runs (same file won't create duplicates)
- Pipeline run history persistence
- Structured logging throughout

Rerun Safety:
- File hash is checked before ingestion — same file is not re-ingested
- Curated transactions have a unique constraint on (transaction_id, source_system)
- Reconciliation results are stored per pipeline_run_id
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from finflow.core.logging import get_logger
from finflow.db.models import (
    CuratedTransaction,
    IngestionBatch,
    PipelineRun,
    QualityResult,
    RawTransaction,
    ReconciliationResult,
)
from finflow.ingestion.readers import IngestionError, compute_file_hash, read_csv_file
from finflow.ingestion.source_adapters import apply_column_mapping, detect_source_system
from finflow.quality.validation import validate_dataframe
from finflow.reconciliation.matcher import reconcile_transactions
from finflow.transformations.normalize import normalize_dataframe

logger = get_logger(__name__)


class PipelineError(Exception):
    """Raised when the pipeline encounters a fatal error."""

    pass


def _update_run_status(
    db: Session,
    run: PipelineRun,
    status: str,
    stage: str | None = None,
    error: str | None = None,
):
    """Update pipeline run status and commit."""
    run.status = status
    if stage:
        run.current_stage = stage
    if error:
        run.error_message = error[:2000]  # Truncate long errors
    if status in ("SUCCEEDED", "FAILED", "PARTIALLY_SUCCEEDED"):
        now = datetime.now(UTC)
        run.completed_at = now
        if run.started_at:
            started = run.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            delta = now - started
            run.duration_seconds = round(delta.total_seconds(), 2)
    db.commit()


def run_pipeline(
    db: Session,
    source_files: list[Path],
) -> PipelineRun:
    """Execute the complete ETL pipeline.

    Args:
        db: SQLAlchemy session
        source_files: List of file paths to process

    Returns:
        PipelineRun with final status and statistics
    """
    run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
    run = PipelineRun(
        run_id=run_id,
        status="RUNNING",
        started_at=datetime.now(UTC),
        current_stage="EXTRACT",
        source_files=json.dumps([str(f) for f in source_files]),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    logger.info("pipeline_started", run_id=run_id, files=[str(f) for f in source_files])

    all_raw_records = []
    batches = []
    total_input = 0

    try:
        # =====================================================================
        # STAGE 1: EXTRACT
        # =====================================================================
        _update_run_status(db, run, "RUNNING", "EXTRACT")

        for filepath in source_files:
            filepath = Path(filepath)
            file_hash = compute_file_hash(filepath)

            # Check for duplicate file ingestion
            existing_batch = db.execute(
                select(IngestionBatch).where(IngestionBatch.file_hash == file_hash)
            ).scalar_one_or_none()

            if existing_batch:
                logger.warning(
                    "file_already_ingested",
                    file=filepath.name,
                    hash=file_hash[:16],
                    previous_batch=existing_batch.batch_id,
                )
                continue

            # Read file
            df = read_csv_file(filepath)
            source_system = detect_source_system(df)

            # Create ingestion batch
            batch = IngestionBatch(
                batch_id=f"BATCH-{uuid.uuid4().hex[:12].upper()}",
                pipeline_run_id=run.id,
                source_system=source_system,
                filename=filepath.name,
                file_hash=file_hash,
                file_size_bytes=filepath.stat().st_size,
                record_count=len(df),
            )
            db.add(batch)
            db.commit()
            db.refresh(batch)

            # Apply column mapping
            mapped_df = apply_column_mapping(df, source_system)
            mapped_df["_batch_id"] = batch.id
            mapped_df["_source_system"] = source_system
            mapped_df["_filepath"] = str(filepath)

            # Store raw records
            for idx, row in mapped_df.iterrows():
                raw_tx = RawTransaction(
                    batch_id=batch.id,
                    row_number=int(idx) + 1,
                    transaction_id=row.get("transaction_id"),
                    external_reference=row.get("external_reference"),
                    account_id=row.get("account_id"),
                    transaction_date=row.get("transaction_date"),
                    currency=row.get("currency"),
                    amount=row.get("amount"),
                    transaction_type=row.get("transaction_type"),
                    description=row.get("description"),
                    source_system=source_system,
                    raw_data=json.dumps(row.to_dict(), default=str),
                )
                db.add(raw_tx)
                all_raw_records.append(raw_tx)

            db.commit()

            batches.append(batch)
            total_input += len(df)
            mapped_df["_raw_start_idx"] = len(all_raw_records) - len(mapped_df)

            logger.info(
                "file_extracted",
                file=filepath.name,
                source=source_system,
                records=len(df),
            )

        run.records_input = total_input
        raw_lookup = {(r.batch_id, r.row_number): r.id for r in all_raw_records}

        if not batches:
            _update_run_status(
                db,
                run,
                "SUCCEEDED",
                "COMPLETE",
                error="No new files to process (all files previously ingested)",
            )
            return run

        # =====================================================================
        # STAGE 2: TRANSFORM
        # =====================================================================
        _update_run_status(db, run, "RUNNING", "TRANSFORM")

        # Re-read and transform each batch
        all_transformed = []
        for filepath in source_files:
            filepath = Path(filepath)
            file_hash = compute_file_hash(filepath)

            # Find the batch for this file
            batch = None
            for b in batches:
                if b.file_hash == file_hash:
                    batch = b
                    break
            if batch is None:
                continue

            df = read_csv_file(filepath)
            source_system = detect_source_system(df)
            mapped_df = apply_column_mapping(df, source_system)
            transformed_df = normalize_dataframe(mapped_df, source_system)
            transformed_df["_batch_id"] = batch.id
            transformed_df["_row_number"] = list(range(1, len(transformed_df) + 1))
            all_transformed.append(transformed_df)

        import pandas as pd

        if all_transformed:
            combined_df = pd.concat(all_transformed, ignore_index=True)
        else:
            combined_df = pd.DataFrame()

        logger.info("transform_complete", total_records=len(combined_df))

        # =====================================================================
        # STAGE 3: VALIDATE
        # =====================================================================
        _update_run_status(db, run, "RUNNING", "VALIDATE")

        valid_df, rejected_df, quality_results = validate_dataframe(combined_df, run.id)

        # Persist quality results
        for qr in quality_results:
            raw_tx_id = None
            row_idx = qr.get("row_index")
            if row_idx is not None and row_idx < len(combined_df):
                b_id = combined_df.iloc[row_idx].get("_batch_id")
                r_num = combined_df.iloc[row_idx].get("_row_number", row_idx + 1)
                if b_id and r_num:
                    raw_tx_id = raw_lookup.get((int(b_id), int(r_num)))

            qr_model = QualityResult(
                pipeline_run_id=run.id,
                rule_id=qr["rule_id"],
                raw_transaction_id=raw_tx_id,
                source_system=qr.get("source_system"),
                field_name=qr.get("field_name"),
                field_value=str(qr.get("field_value", ""))[:256] if qr.get("field_value") else None,
                passed=qr["passed"],
                severity=qr["severity"],
                failure_reason=qr.get("failure_reason"),
            )
            db.add(qr_model)

        db.commit()

        run.records_processed = len(combined_df)
        run.records_accepted = len(valid_df)
        run.records_rejected = len(rejected_df)

        logger.info(
            "validation_complete",
            accepted=len(valid_df),
            rejected=len(rejected_df),
        )

        # =====================================================================
        # STAGE 4: LOAD curated transactions
        # =====================================================================
        _update_run_status(db, run, "RUNNING", "LOAD")

        # Cache existing curated transactions for fast idempotency check
        existing_rows = db.execute(
            select(CuratedTransaction.transaction_id, CuratedTransaction.source_system)
        ).all()
        existing_keys = {(r[0], r[1]) for r in existing_rows}

        loaded_count = 0
        for _, row in valid_df.iterrows():
            batch_id = row.get("_batch_id")
            row_num = row.get("_row_number", 0)
            raw_tx_id = (
                raw_lookup.get((int(batch_id), int(row_num))) if batch_id and row_num else None
            )

            if not raw_tx_id:
                continue

            if (row["transaction_id"], row["source_system"]) in existing_keys:
                logger.debug(
                    "curated_already_exists",
                    tx_id=row["transaction_id"],
                    source=row["source_system"],
                )
                continue

            # Ensure pure Python datetime object
            tx_date = row["date_parsed"]
            if hasattr(tx_date, "to_pydatetime"):
                tx_date = tx_date.to_pydatetime()

            curated = CuratedTransaction(
                raw_transaction_id=raw_tx_id,
                pipeline_run_id=run.id,
                transaction_id=row["transaction_id"],
                external_reference=row.get("external_reference"),
                account_id=row["account_id"],
                transaction_date=tx_date,
                currency=row["currency_normalized"],
                amount=row["amount_decimal"],
                transaction_type=row["type_normalized"],
                description=row.get("description"),
                source_system=row["source_system"],
            )
            db.add(curated)
            loaded_count += 1
            existing_keys.add((row["transaction_id"], row["source_system"]))

        db.commit()
        run.records_loaded = loaded_count

        logger.info("load_complete", loaded=loaded_count)

        # =====================================================================
        # STAGE 5: RECONCILE
        # =====================================================================
        _update_run_status(db, run, "RUNNING", "RECONCILE")

        # Fetch curated records for this run
        source_a_curated = (
            db.execute(
                select(CuratedTransaction).where(
                    CuratedTransaction.pipeline_run_id == run.id,
                    CuratedTransaction.source_system == "SOURCE_A",
                )
            )
            .scalars()
            .all()
        )

        source_b_curated = (
            db.execute(
                select(CuratedTransaction).where(
                    CuratedTransaction.pipeline_run_id == run.id,
                    CuratedTransaction.source_system == "SOURCE_B",
                )
            )
            .scalars()
            .all()
        )

        a_records = [
            {
                "id": t.id,
                "external_reference": t.external_reference,
                "amount": t.amount,
                "currency": t.currency,
                "account_id": t.account_id,
                "transaction_date": t.transaction_date,
            }
            for t in source_a_curated
        ]
        b_records = [
            {
                "id": t.id,
                "external_reference": t.external_reference,
                "amount": t.amount,
                "currency": t.currency,
                "account_id": t.account_id,
                "transaction_date": t.transaction_date,
            }
            for t in source_b_curated
        ]

        recon_results, recon_summary = reconcile_transactions(a_records, b_records)

        # Persist reconciliation results
        for rr in recon_results:
            recon_model = ReconciliationResult(
                pipeline_run_id=run.id,
                source_a_transaction_id=rr.source_a_id,
                source_b_transaction_id=rr.source_b_id,
                external_reference=rr.external_reference,
                status=rr.status,
                source_a_amount=rr.source_a_amount,
                source_b_amount=rr.source_b_amount,
                amount_difference=rr.amount_difference,
                currency=rr.currency,
                mismatch_reason=rr.mismatch_reason,
            )
            db.add(recon_model)

        db.commit()

        # =====================================================================
        # COMPLETE
        # =====================================================================
        final_status = "SUCCEEDED"
        if run.records_rejected > 0:
            final_status = "PARTIALLY_SUCCEEDED"

        _update_run_status(db, run, final_status, "COMPLETE")
        db.commit()

        logger.info(
            "pipeline_complete",
            run_id=run_id,
            status=final_status,
            input=run.records_input,
            accepted=run.records_accepted,
            rejected=run.records_rejected,
            loaded=run.records_loaded,
            recon_matched=recon_summary.matched,
            recon_mismatches=recon_summary.amount_mismatches,
        )

        return run

    except IngestionError as e:
        logger.error("pipeline_ingestion_error", run_id=run_id, error=str(e))
        _update_run_status(db, run, "FAILED", error=str(e))
        return run

    except Exception as e:
        logger.error("pipeline_error", run_id=run_id, error=str(e))
        _update_run_status(db, run, "FAILED", error=str(e)[:2000])
        db.rollback()
        # Re-fetch run after rollback
        run = db.execute(select(PipelineRun).where(PipelineRun.run_id == run_id)).scalar_one()
        _update_run_status(db, run, "FAILED", error=str(e)[:2000])
        return run
