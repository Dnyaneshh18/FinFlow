"""Script to run the ETL pipeline from the command line.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --files data/sample/source_a_transactions.csv data/sample/source_b_transactions.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from finflow.core.config import get_settings
from finflow.core.logging import get_logger, setup_logging
from finflow.db.session import create_all_tables, get_session_factory
from finflow.pipelines.orchestrator import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Run the FinFlow ETL pipeline")
    parser.add_argument(
        "--files",
        nargs="+",
        help="Source CSV files to process. Defaults to sample data.",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate sample data before running the pipeline",
    )
    args = parser.parse_args()

    setup_logging()
    logger = get_logger("run_pipeline")
    settings = get_settings()

    # Ensure tables exist
    create_all_tables()

    # Generate sample data if requested
    if args.generate:
        from scripts.generate_sample_data import generate_sample_data

        source_a, source_b = generate_sample_data()
        logger.info("sample_data_generated", source_a=str(source_a), source_b=str(source_b))

    # Determine files to process
    if args.files:
        files = [Path(f) for f in args.files]
    else:
        files = [
            settings.sample_data_dir / "source_a_transactions.csv",
            settings.sample_data_dir / "source_b_transactions.csv",
        ]

    # Validate files exist
    for f in files:
        if not f.exists():
            logger.error("file_not_found", file=str(f))
            print(f"Error: File not found: {f}")
            print("Run with --generate to create sample data first.")
            sys.exit(1)

    # Run pipeline
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        run = run_pipeline(db, files)
        print(f"\n{'=' * 60}")
        print(f"Pipeline Run: {run.run_id}")
        print(f"Status:       {run.status}")
        print(f"Records In:   {run.records_input}")
        print(f"Accepted:     {run.records_accepted}")
        print(f"Rejected:     {run.records_rejected}")
        print(f"Loaded:       {run.records_loaded}")
        print(f"Duration:     {run.duration_seconds}s")
        if run.error_message:
            print(f"Error:        {run.error_message}")
        print(f"{'=' * 60}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
