"""FinFlow Streamlit Dashboard.

Professional data engineering dashboard for pipeline monitoring,
data quality analysis, and reconciliation reporting.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import func, select

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from finflow.core.config import get_settings
from finflow.db.models import (
    CuratedTransaction,
    PipelineRun,
    QualityResult,
    RawTransaction,
    ReconciliationResult,
)
from finflow.db.session import create_all_tables, get_session_factory

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FinFlow — ETL & Reconciliation Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
    .main > div { padding-top: 1rem; }
    .stMetric { background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
                padding: 1rem; border-radius: 0.75rem; border: 1px solid #475569; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; }
    .status-badge { display: inline-block; padding: 0.25rem 0.75rem;
                    border-radius: 1rem; font-size: 0.8rem; font-weight: 600; }
    .status-succeeded { background: #065f46; color: #6ee7b7; }
    .status-failed { background: #7f1d1d; color: #fca5a5; }
    .status-partial { background: #78350f; color: #fcd34d; }
    .status-running { background: #1e3a5f; color: #93c5fd; }
</style>
""",
    unsafe_allow_html=True,
)


def get_db():
    """Get a database session."""
    create_all_tables()
    SessionLocal = get_session_factory()
    return SessionLocal()


def status_badge(status: str) -> str:
    """Generate HTML badge for pipeline status."""
    cls = {
        "SUCCEEDED": "status-succeeded",
        "FAILED": "status-failed",
        "PARTIALLY_SUCCEEDED": "status-partial",
        "RUNNING": "status-running",
        "PENDING": "status-running",
    }.get(status, "")
    return f'<span class="status-badge {cls}">{status}</span>'


# ─── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("💰 FinFlow")
st.sidebar.markdown("**Financial ETL & Reconciliation**")

page = st.sidebar.radio(
    "Navigation",
    [
        "📊 Overview",
        "🔄 Pipeline Runs",
        "✅ Data Quality",
        "🔗 Reconciliation",
        "📋 Transaction Explorer",
        "🚀 Run Pipeline",
        "📖 Documentation",
    ],
)

st.sidebar.markdown("---")
st.sidebar.caption("FinFlow v0.1.0 | Synthetic Data Only")

# ─── Database session ─────────────────────────────────────────────────────────
db = get_db()

# ═══════════════════════════════════════════════════════════════════════════════
# OVERVIEW PAGE
# ═══════════════════════════════════════════════════════════════════════════════
if page == "📊 Overview":
    st.title("📊 Pipeline Overview")
    st.markdown("Real-time operational status of the FinFlow ETL platform.")

    # Key metrics
    total_runs = db.execute(select(func.count()).select_from(PipelineRun)).scalar() or 0
    succeeded = (
        db.execute(
            select(func.count()).select_from(PipelineRun).where(PipelineRun.status == "SUCCEEDED")
        ).scalar()
        or 0
    )
    partial = (
        db.execute(
            select(func.count())
            .select_from(PipelineRun)
            .where(PipelineRun.status == "PARTIALLY_SUCCEEDED")
        ).scalar()
        or 0
    )
    failed = (
        db.execute(
            select(func.count()).select_from(PipelineRun).where(PipelineRun.status == "FAILED")
        ).scalar()
        or 0
    )
    total_curated = db.execute(select(func.count()).select_from(CuratedTransaction)).scalar() or 0
    total_raw = db.execute(select(func.count()).select_from(RawTransaction)).scalar() or 0
    total_quality_fails = (
        db.execute(
            select(func.count()).select_from(QualityResult).where(QualityResult.passed.is_(False))
        ).scalar()
        or 0
    )
    total_matched = (
        db.execute(
            select(func.count())
            .select_from(ReconciliationResult)
            .where(ReconciliationResult.status == "MATCHED")
        ).scalar()
        or 0
    )
    total_recon = db.execute(select(func.count()).select_from(ReconciliationResult)).scalar() or 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pipeline Runs", total_runs, f"✅ {succeeded + partial} succeeded")
    col2.metric("Curated Records", total_curated, f"📥 {total_raw} raw ingested")
    col3.metric("Quality Issues", total_quality_fails, "❗ Failed checks")
    match_rate = round(total_matched / total_recon * 100, 1) if total_recon > 0 else 0
    col4.metric("Match Rate", f"{match_rate}%", f"{total_matched}/{total_recon} matched")

    st.markdown("---")

    # Recent runs table
    st.subheader("Recent Pipeline Runs")
    runs = (
        db.execute(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(10))
        .scalars()
        .all()
    )

    if runs:
        runs_data = []
        for r in runs:
            runs_data.append(
                {
                    "Run ID": r.run_id,
                    "Status": r.status,
                    "Started": r.started_at.strftime("%Y-%m-%d %H:%M") if r.started_at else "—",
                    "Input": r.records_input,
                    "Accepted": r.records_accepted,
                    "Rejected": r.records_rejected,
                    "Duration (s)": float(r.duration_seconds) if r.duration_seconds else 0,
                }
            )
        st.dataframe(pd.DataFrame(runs_data), use_container_width=True, hide_index=True)
    else:
        st.info("No pipeline runs yet. Go to **🚀 Run Pipeline** to start one.")

    # Charts
    if total_recon > 0:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Reconciliation Status")
            recon_data = db.execute(
                select(
                    ReconciliationResult.status,
                    func.count().label("count"),
                ).group_by(ReconciliationResult.status)
            ).all()
            if recon_data:
                fig = px.pie(
                    values=[r[1] for r in recon_data],
                    names=[r[0] for r in recon_data],
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    hole=0.4,
                )
                fig.update_layout(
                    margin=dict(l=20, r=20, t=30, b=20),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                    height=350,
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Records by Source")
            source_data = db.execute(
                select(
                    CuratedTransaction.source_system,
                    func.count().label("count"),
                ).group_by(CuratedTransaction.source_system)
            ).all()
            if source_data:
                fig = px.bar(
                    x=[r[0] for r in source_data],
                    y=[r[1] for r in source_data],
                    color=[r[0] for r in source_data],
                    color_discrete_sequence=["#3b82f6", "#10b981"],
                )
                fig.update_layout(
                    margin=dict(l=20, r=20, t=30, b=20),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                    showlegend=False,
                    xaxis_title="Source System",
                    yaxis_title="Record Count",
                    height=350,
                )
                st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE RUNS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🔄 Pipeline Runs":
    st.title("🔄 Pipeline Run History")

    status_filter = st.selectbox(
        "Filter by status",
        ["All", "SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "RUNNING", "PENDING"],
    )

    query = select(PipelineRun).order_by(PipelineRun.started_at.desc())
    if status_filter != "All":
        query = query.where(PipelineRun.status == status_filter)

    runs = db.execute(query).scalars().all()

    if runs:
        for r in runs:
            with st.expander(f"{r.run_id} — {r.status}", expanded=False):
                col1, col2, col3 = st.columns(3)
                col1.write(f"**Started:** {r.started_at}")
                col2.write(f"**Completed:** {r.completed_at or 'In progress'}")
                col3.write(f"**Duration:** {r.duration_seconds or 0}s")

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Input", r.records_input)
                col2.metric("Accepted", r.records_accepted)
                col3.metric("Rejected", r.records_rejected)
                col4.metric("Loaded", r.records_loaded)

                if r.error_message:
                    st.error(f"Error: {r.error_message}")
                if r.source_files:
                    st.write(f"**Files:** {r.source_files}")
    else:
        st.info("No pipeline runs match the selected filter.")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA QUALITY PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "✅ Data Quality":
    st.title("✅ Data Quality Analysis")

    # Summary metrics
    total_checks = db.execute(select(func.count()).select_from(QualityResult)).scalar() or 0
    passed = (
        db.execute(
            select(func.count()).select_from(QualityResult).where(QualityResult.passed.is_(True))
        ).scalar()
        or 0
    )
    errors = (
        db.execute(
            select(func.count())
            .select_from(QualityResult)
            .where(QualityResult.passed.is_(False), QualityResult.severity == "ERROR")
        ).scalar()
        or 0
    )
    warnings = (
        db.execute(
            select(func.count())
            .select_from(QualityResult)
            .where(QualityResult.passed.is_(False), QualityResult.severity == "WARNING")
        ).scalar()
        or 0
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Checks", total_checks)
    col2.metric("Passed", passed)
    col3.metric("Errors", errors)
    col4.metric("Warnings", warnings)

    st.markdown("---")

    # Failures by rule
    st.subheader("Failures by Rule")
    rule_data = db.execute(
        select(
            QualityResult.rule_id,
            QualityResult.severity,
            func.count().label("count"),
        )
        .where(QualityResult.passed.is_(False))
        .group_by(QualityResult.rule_id, QualityResult.severity)
        .order_by(func.count().desc())
    ).all()

    if rule_data:
        fig = px.bar(
            x=[r[0] for r in rule_data],
            y=[r[2] for r in rule_data],
            color=[r[1] for r in rule_data],
            color_discrete_map={"ERROR": "#ef4444", "WARNING": "#f59e0b", "INFO": "#3b82f6"},
            labels={"x": "Rule", "y": "Count", "color": "Severity"},
        )
        fig.update_layout(
            margin=dict(l=20, r=20, t=30, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Recent failures
    st.subheader("Recent Quality Issues")
    issues = (
        db.execute(
            select(QualityResult)
            .where(QualityResult.passed.is_(False))
            .order_by(QualityResult.id.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )

    if issues:
        issues_data = []
        for i in issues:
            issues_data.append(
                {
                    "Rule": i.rule_id,
                    "Severity": i.severity,
                    "Field": i.field_name or "—",
                    "Value": (i.field_value or "—")[:50],
                    "Reason": (i.failure_reason or "—")[:80],
                    "Source": i.source_system or "—",
                }
            )
        st.dataframe(pd.DataFrame(issues_data), use_container_width=True, hide_index=True)
    else:
        st.success("No quality issues found! All records passed validation.")


# ═══════════════════════════════════════════════════════════════════════════════
# RECONCILIATION PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🔗 Reconciliation":
    st.title("🔗 Financial Reconciliation")

    total_recon = db.execute(select(func.count()).select_from(ReconciliationResult)).scalar() or 0
    matched = (
        db.execute(
            select(func.count())
            .select_from(ReconciliationResult)
            .where(ReconciliationResult.status == "MATCHED")
        ).scalar()
        or 0
    )
    mismatches = (
        db.execute(
            select(func.count())
            .select_from(ReconciliationResult)
            .where(ReconciliationResult.status == "AMOUNT_MISMATCH")
        ).scalar()
        or 0
    )
    missing_a = (
        db.execute(
            select(func.count())
            .select_from(ReconciliationResult)
            .where(ReconciliationResult.status == "MISSING_IN_SOURCE_A")
        ).scalar()
        or 0
    )
    missing_b = (
        db.execute(
            select(func.count())
            .select_from(ReconciliationResult)
            .where(ReconciliationResult.status == "MISSING_IN_SOURCE_B")
        ).scalar()
        or 0
    )
    ambiguous = (
        db.execute(
            select(func.count())
            .select_from(ReconciliationResult)
            .where(ReconciliationResult.status == "AMBIGUOUS_MATCH")
        ).scalar()
        or 0
    )

    col1, col2, col3 = st.columns(3)
    match_rate = round(matched / total_recon * 100, 1) if total_recon > 0 else 0
    col1.metric("Match Rate", f"{match_rate}%", f"{matched} matched")
    col2.metric("Amount Mismatches", mismatches)
    col3.metric("Missing Records", missing_a + missing_b)

    col1, col2, col3 = st.columns(3)
    col1.metric("Missing in Source A", missing_a)
    col2.metric("Missing in Source B", missing_b)
    col3.metric("Ambiguous Matches", ambiguous)

    st.markdown("---")

    # Exceptions table
    st.subheader("Reconciliation Exceptions")
    status_filter = st.selectbox(
        "Filter by status",
        [
            "All Exceptions",
            "AMOUNT_MISMATCH",
            "MISSING_IN_SOURCE_A",
            "MISSING_IN_SOURCE_B",
            "AMBIGUOUS_MATCH",
        ],
        key="recon_filter",
    )

    exc_query = (
        select(ReconciliationResult)
        .where(ReconciliationResult.status != "MATCHED")
        .order_by(ReconciliationResult.id.desc())
        .limit(100)
    )

    if status_filter != "All Exceptions":
        exc_query = (
            select(ReconciliationResult)
            .where(ReconciliationResult.status == status_filter)
            .order_by(ReconciliationResult.id.desc())
            .limit(100)
        )

    exceptions = db.execute(exc_query).scalars().all()

    if exceptions:
        exc_data = []
        for e in exceptions:
            exc_data.append(
                {
                    "Status": e.status,
                    "Reference": e.external_reference or "—",
                    "Source A Amount": float(e.source_a_amount) if e.source_a_amount else None,
                    "Source B Amount": float(e.source_b_amount) if e.source_b_amount else None,
                    "Difference": float(e.amount_difference) if e.amount_difference else None,
                    "Currency": e.currency or "—",
                    "Reason": (e.mismatch_reason or "—")[:80],
                }
            )
        st.dataframe(pd.DataFrame(exc_data), use_container_width=True, hide_index=True)
    else:
        st.success("No reconciliation exceptions — all records matched!")


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSACTION EXPLORER PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📋 Transaction Explorer":
    st.title("📋 Transaction Explorer")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        source_filter = st.selectbox("Source", ["All", "SOURCE_A", "SOURCE_B"])
    with col2:
        currency_filter = st.selectbox("Currency", ["All", "USD", "EUR", "GBP", "JPY", "CAD"])
    with col3:
        type_filter = st.selectbox(
            "Type", ["All", "CREDIT", "DEBIT", "TRANSFER", "REVERSAL", "FEE", "ADJUSTMENT"]
        )
    with col4:
        page_num = st.number_input("Page", min_value=1, value=1)

    query = select(CuratedTransaction).order_by(CuratedTransaction.transaction_date.desc())
    if source_filter != "All":
        query = query.where(CuratedTransaction.source_system == source_filter)
    if currency_filter != "All":
        query = query.where(CuratedTransaction.currency == currency_filter)
    if type_filter != "All":
        query = query.where(CuratedTransaction.transaction_type == type_filter)

    page_size = 25
    offset = (page_num - 1) * page_size
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0

    transactions = db.execute(query.offset(offset).limit(page_size)).scalars().all()

    st.caption(f"Showing {len(transactions)} of {total} transactions (page {page_num})")

    if transactions:
        tx_data = []
        for t in transactions:
            tx_data.append(
                {
                    "Transaction ID": t.transaction_id,
                    "Reference": t.external_reference or "—",
                    "Account": t.account_id,
                    "Date": t.transaction_date.strftime("%Y-%m-%d %H:%M")
                    if t.transaction_date
                    else "—",
                    "Currency": t.currency,
                    "Amount": float(t.amount),
                    "Type": t.transaction_type,
                    "Source": t.source_system,
                }
            )
        st.dataframe(pd.DataFrame(tx_data), use_container_width=True, hide_index=True)
    else:
        st.info("No transactions found with the selected filters.")

    # Summary statistics
    if total > 0:
        st.markdown("---")
        st.subheader("Summary Statistics")
        stats = db.execute(
            select(
                CuratedTransaction.currency,
                CuratedTransaction.transaction_type,
                func.count().label("count"),
                func.sum(CuratedTransaction.amount).label("total"),
            )
            .group_by(
                CuratedTransaction.currency,
                CuratedTransaction.transaction_type,
            )
            .order_by(func.count().desc())
        ).all()
        if stats:
            stats_data = []
            for s in stats:
                stats_data.append(
                    {
                        "Currency": s[0],
                        "Type": s[1],
                        "Count": s[2],
                        "Total Amount": float(s[3]) if s[3] else 0,
                    }
                )
            st.dataframe(pd.DataFrame(stats_data), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# RUN PIPELINE PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🚀 Run Pipeline":
    st.title("🚀 Run Pipeline")
    st.markdown("Trigger a new ETL pipeline execution using sample data files.")

    settings = get_settings()
    sample_dir = settings.sample_data_dir

    # Option 1: Use sample data
    st.subheader("📁 Use Sample Data")
    sample_files = list(sample_dir.glob("*.csv")) if sample_dir.exists() else []

    if sample_files:
        selected = st.multiselect(
            "Select source files",
            [f.name for f in sample_files],
            default=[f.name for f in sample_files],
        )

        if st.button("⚠️ Run Pipeline", type="primary"):
            if not selected:
                st.warning("Please select at least one file.")
            else:
                with st.spinner("Running pipeline..."):
                    from finflow.pipelines.orchestrator import run_pipeline

                    files = [sample_dir / name for name in selected]
                    run = run_pipeline(db, files)

                    if run.status in ("SUCCEEDED", "PARTIALLY_SUCCEEDED"):
                        st.success(f"Pipeline completed: **{run.run_id}**")
                    else:
                        st.error(f"Pipeline failed: {run.error_message}")

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Status", run.status)
                    col2.metric("Accepted", run.records_accepted)
                    col3.metric("Rejected", run.records_rejected)
                    col4.metric("Duration", f"{run.duration_seconds}s")
    else:
        st.warning(
            f"No sample files found in `{sample_dir}`. "
            "Run `python scripts/generate_sample_data.py` first."
        )

    # Option 2: Generate sample data
    st.markdown("---")
    st.subheader("🔧 Generate Sample Data")
    num_tx = st.slider("Number of transactions", 100, 2000, 500, step=100)
    seed = st.number_input("Random seed", value=42)

    if st.button("Generate Data"):
        with st.spinner("Generating synthetic data..."):
            from scripts.generate_sample_data import generate_sample_data

            a, b = generate_sample_data(num_transactions=num_tx, seed=seed)
            st.success(f"Generated:\n- {a}\n- {b}")
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENTATION PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📖 Documentation":
    st.title("📖 Documentation")

    st.markdown("""
    ## Pipeline Stages

    1. **Extract**: Read CSV files, validate structure, compute file hash for deduplication.
    2. **Transform**: Normalize column names, dates (UTC), amounts (Decimal), currencies, types.
    3. **Validate**: Run quality rules (required fields, valid formats, duplicates).
    4. **Load**: Persist curated transactions with unique constraints.
    5. **Reconcile**: Match Source A ↔ Source B by external reference.

    ## Matching Rules

    - **Primary Key**: `external_reference` — exact match between sources.
    - **Amount Comparison**: Exact Decimal arithmetic (not floating-point).
    - **Currency**: Must match exactly.
    - **Ambiguity**: Multiple B matches for one reference → `AMBIGUOUS_MATCH`.

    ## Data Quality Rules

    | Rule | Severity | Description |
    |------|----------|-------------|
    | `REQUIRED_TRANSACTION_ID` | ERROR | Transaction ID must be non-empty |
    | `REQUIRED_ACCOUNT_ID` | ERROR | Account ID must be non-empty |
    | `VALID_AMOUNT` | ERROR | Amount must be a valid decimal number |
    | `VALID_CURRENCY` | ERROR | Must be USD, EUR, GBP, JPY, CAD, AUD, CHF |
    | `VALID_DATE` | ERROR | Must be a parseable date |
    | `DATE_NOT_FUTURE` | WARNING | Should not be in the future |
    | `VALID_TRANSACTION_TYPE` | WARNING | Must be CREDIT, DEBIT, TRANSFER, etc. |
    | `DUPLICATE_DETECTION` | ERROR | Same (transaction_id, source_system) pair |
    | `EXTERNAL_REFERENCE_PRESENT` | WARNING | Missing reference affects reconciliation |

    ## Reconciliation Outcomes

    | Status | Meaning |
    |--------|---------|
    | `MATCHED` | Same reference, amount, and currency in both sources |
    | `AMOUNT_MISMATCH` | Same reference but different amounts |
    | `MISSING_IN_SOURCE_A` | Only in Source B |
    | `MISSING_IN_SOURCE_B` | Only in Source A |
    | `AMBIGUOUS_MATCH` | Multiple candidates in Source B |

    ## Known Limitations

    - This is a portfolio project using synthetic data only.
    - No real financial data or regulatory compliance.
    - Authentication is not implemented (demo mode).
    - Date matching is at date level (no time tolerance).
    """)

# Close DB
db.close()
