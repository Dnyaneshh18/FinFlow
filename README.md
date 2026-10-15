# FinFlow — Financial Data ETL & Reconciliation Platform

[![CI Pipeline](https://github.com/Dnyaneshh18/FinFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/Dnyaneshh18/FinFlow/actions)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL 16](https://img.shields.io/badge/postgresql-16-336791.svg)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-FF4B4B.svg)](https://streamlit.io)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**FinFlow** is an enterprise-grade financial data engineering and reconciliation platform. It ingests transaction feeds from heterogeneous financial systems, normalizes and validates data quality with configurable rule engines, loads standardized records into PostgreSQL with strict idempotency and auditability, reconciles multi-source ledgers with exact decimal arithmetic, and visualizes pipeline health and variance exceptions through an interactive dashboard and RESTful API.

---

## 🏛 Architecture Overview

```
                                      +------------------------------------+
                                      |         External Feeds             |
                                      |  Source A (Core) / Source B (Bank) |
                                      +-----------------+------------------+
                                                        |
                                                        v
+-------------------------------------------------------------------------------------------------------+
|                                        FinFlow ETL Engine                                             |
|                                                                                                       |
|  [ Stage 1: Extract & Audit ]                                                                         |
|      * SHA-256 Checksum hashing (file-level deduplication & idempotency)                             |
|      * Content verification & schema auto-detection                                                   |
|      * Raw record capture in `raw_transactions` table with full JSON payload audit                    |
|                                       |                                                               |
|                                       v                                                               |
|  [ Stage 2: Transform & Normalize ]                                                                   |
|      * Column mapping adapter (Source-specific -> FinFlow canonical schema)                           |
|      * Deterministic string cleansing & whitespace trimming                                          |
|      * Multi-format date parsing to UTC timezone                                                      |
|      * ISO 4217 currency & transaction type normalization                                             |
|      * Fixed-point Decimal parsing (preserves exact precision up to 4 decimal places)                 |
|                                       |                                                               |
|                                       v                                                               |
|  [ Stage 3: Data Quality Validation ]                                                                 |
|      * Business key duplicate detection `(transaction_id, source_system)`                             |
|      * Mandatory field presence checks (ID, Account, Amount, Currency, Date, Type)                    |
|      * Anomaly detection (non-future dates, zero-amount handling)                                     |
|      * Severity categorization (`ERROR` -> rejected, `WARNING` -> accepted with audit)               |
|      * Individual check recording in `quality_results` table                                          |
|                                       |                                                               |
|                                       v                                                               |
|  [ Stage 4: Curated Loading ]                                                                         |
|      * Atomic transactional batch load into `curated_transactions`                                    |
|      * Idempotent insertion guard: skips existing business keys without error                         |
|      * Audit linkage: FK back to `raw_transactions.id` & `pipeline_runs.id`                           |
|                                       |                                                               |
|                                       v                                                               |
|  [ Stage 5: Reconciliation Engine ]                                                                   |
|      * Cross-system transaction matching by `external_reference`                                      |
|      * Tolerance-aware amount difference calculation (`Decimal(18, 4)`)                               |
|      * Multi-way outcome classification:                                                              |
|          - MATCHED: Reference & amount agree                                                          |
|          - AMOUNT_MISMATCH: Same reference, amount variance recorded                                  |
|          - MISSING_IN_SOURCE_A / MISSING_IN_SOURCE_B: Unilateral records                              |
|          - AMBIGUOUS_MATCH: Multiple records share identical reference                                |
|      * Exception persistence in `reconciliation_results`                                              |
+-------------------------------------------------------------------------------------------------------+
                                        |
                   +--------------------+--------------------+
                   |                                         |
                   v                                         v
+------------------------------------+    +------------------------------------+
|          FastAPI REST API          |    |        Streamlit Dashboard         |
|  * Runs, Transactions, Quality     |    |  * Executive KPI cards             |
|  * Reconciliation Variance Reports |    |  * Reconciliation matrix & charts  |
|  * Interactive OpenAPI Swagger UI  |    |  * Interactive Exception Explorer  |
+------------------------------------+    +------------------------------------+
```

---

## 💎 Key Features

- **Production-Grade Data Pipeline**: End-to-end extraction, transformation, quality gates, database loading, and reconciliation.
- **Strict Idempotency**: SHA-256 file hashing prevents duplicate ingestions; unique database constraints and in-memory caches prevent double-counting.
- **Exact Decimal Arithmetic**: Uses Python `Decimal` and PostgreSQL `NUMERIC(18, 4)` for financial calculations. Zero float rounding errors.
- **Multi-Source Ingestion**: Adaptable readers supporting Source A (Core Banking) and Source B (Partner Bank / Payment Gateway) formats.
- **Granular Data Quality Auditing**: Every record undergoes 8 validation rules. Checks are recorded per-field with error/warning severities.
- **Intelligent Ledger Reconciliation**: Matches transactions across sources and detects amount mismatches, orphan records, and duplicates.
- **Interactive Analytics UI**: Modern Streamlit application with interactive Plotly visualisations, exception drill-downs, and manual pipeline triggers.
- **Production REST API**: FastAPI server providing paginated access, query filtering, and health endpoints.
- **Comprehensive Test Coverage**: 94 unit & integration tests covering 100% of core business logic.
- **Containerized & CI/CD Ready**: Dockerfile, `docker-compose.yml`, and GitHub Actions workflow for automated testing and linting.

---

## 🗄 Database Schema

The database model is managed via **Alembic** and **SQLAlchemy 2.0**:

```mermaid
erDiagram
    PIPELINE_RUNS ||--o{ INGESTION_BATCHES : "tracks"
    PIPELINE_RUNS ||--o{ QUALITY_RESULTS : "records"
    PIPELINE_RUNS ||--o{ RECONCILIATION_RESULTS : "produces"
    INGESTION_BATCHES ||--o{ RAW_TRANSACTIONS : "contains"
    RAW_TRANSACTIONS ||--o| CURATED_TRANSACTIONS : "curates into"
    RAW_TRANSACTIONS ||--o{ QUALITY_RESULTS : "audits"
    CURATED_TRANSACTIONS ||--o{ RECONCILIATION_RESULTS : "matched in"

    PIPELINE_RUNS {
        int id PK
        string run_id UK
        string status
        timestamp started_at
        timestamp completed_at
        int records_input
        int records_accepted
        int records_rejected
        int records_loaded
        numeric duration_seconds
    }

    INGESTION_BATCHES {
        int id PK
        string batch_id UK
        int pipeline_run_id FK
        string source_system
        string filename
        string file_hash
        int record_count
    }

    RAW_TRANSACTIONS {
        int id PK
        int batch_id FK
        int row_number
        string transaction_id
        string external_reference
        string amount
        string currency
        text raw_data
    }

    CURATED_TRANSACTIONS {
        int id PK
        int raw_transaction_id FK
        int pipeline_run_id FK
        string transaction_id
        string external_reference
        string account_id
        timestamp transaction_date
        string currency
        numeric amount
        string transaction_type
        string source_system
    }

    QUALITY_RESULTS {
        int id PK
        int pipeline_run_id FK
        int raw_transaction_id FK
        string rule_id
        string severity
        boolean passed
        string failure_reason
    }

    RECONCILIATION_RESULTS {
        int id PK
        int pipeline_run_id FK
        int source_a_transaction_id FK
        int source_b_transaction_id FK
        string external_reference
        string status
        numeric source_a_amount
        numeric source_b_amount
        numeric amount_difference
        string mismatch_reason
    }
```

---

## 🚀 Quickstart

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (or Docker)
- Git

### 1. Clone & Set Up Environment

```bash
git clone https://github.com/Dnyaneshh18/FinFlow.git
cd FinFlow

# Create virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies in editable mode
pip install -e ".[dev]"
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure your PostgreSQL connection:

```bash
cp .env.example .env
```

Edit `.env`:
```ini
DATABASE_URL=postgresql+psycopg://postgres:your_password@127.0.0.1:5432/finflow
APP_ENV=development
APP_DEBUG=false
API_PORT=8000
DASHBOARD_PORT=8501
```

### 3. Apply Database Migrations

```bash
# Run Alembic migrations to create tables and indexes
python -m alembic upgrade head
```

### 4. Generate Realistic Sample Feeds

```bash
# Generates Source A and Source B synthetic data with realistic anomalies
python scripts/generate_sample_data.py --count 500
```

### 5. Run the ETL & Reconciliation Pipeline

```bash
python scripts/run_pipeline.py --files data/sample/source_a_transactions.csv data/sample/source_b_transactions.csv
```

Example Pipeline Output:
```text
============================================================
Pipeline Run: RUN-198022403719
Status:       PARTIALLY_SUCCEEDED
Records In:   827
Accepted:     802
Rejected:     25
Loaded:       802
Duration:     6.27s
============================================================
```

---

## 🖥 Running Services

### Start FastAPI REST API

```bash
uvicorn finflow.api.app:app --host 0.0.0.0 --port 8000 --reload
```
Interactive OpenAPI documentation available at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Start Streamlit Analytics Dashboard

```bash
streamlit run finflow/dashboard/app.py --server.port 8501
```
Open your browser to: [http://localhost:8501](http://localhost:8501)

---

## 🐳 Running with Docker Compose

To launch PostgreSQL, FastAPI, and Streamlit together with zero local dependencies:

```bash
docker-compose up --build
```

- **PostgreSQL**: `localhost:5432`
- **FastAPI**: `http://localhost:8000/docs`
- **Dashboard**: `http://localhost:8501`

---

## 📡 REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service and database health check |
| `GET` | `/api/v1/pipeline-runs` | List execution runs (paginated, filterable by status) |
| `GET` | `/api/v1/pipeline-runs/{run_id}` | Detailed status and record counts for a run |
| `POST`| `/api/v1/pipeline-runs` | Trigger pipeline run on specified source files |
| `GET` | `/api/v1/transactions` | Curated transactions (paginated, filter by source, account, date range) |
| `GET` | `/api/v1/transactions/{id}` | Single curated transaction details |
| `GET` | `/api/v1/quality/summary` | Aggregate DQ metrics, error rates, and top failing rules |
| `GET` | `/api/v1/quality/issues` | Detailed list of validation failures (by severity, rule) |
| `GET` | `/api/v1/reconciliation/summary` | Match rates, total reconciled balances, and variances |
| `GET` | `/api/v1/reconciliation/exceptions` | Detailed exception ledger (mismatches, missing records) |
| `GET` | `/api/v1/batches` | Ingestion batch history and SHA-256 file hashes |

---

## 🧪 Testing & Code Quality

The test suite includes comprehensive unit tests and full database integration tests:

```bash
# Run complete test suite (94 tests)
python -m pytest

# Run with test coverage report
python -m pytest --cov=finflow --cov-report=term-missing

# Run Ruff linter
python -m ruff check finflow tests scripts

# Check formatting
python -m ruff format --check finflow tests scripts
```

---

## 📁 Repository Structure

```
FinFlow/
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI workflow
├── data/
│   └── sample/                  # Generated sample CSV files
├── finflow/
│   ├── api/                     # FastAPI REST API
│   │   ├── routes/              # Modular endpoint definitions
│   │   ├── app.py               # Application factory & lifespan
│   │   └── dependencies.py      # Dependency injection (DB session)
│   ├── core/                    # Core configuration and logging
│   │   ├── config.py            # Pydantic Settings management
│   │   └── logging.py           # Structlog structured logger
│   ├── dashboard/               # Streamlit web application
│   │   └── app.py               # Dashboard layout, metrics & charts
│   ├── db/                      # Database layer
│   │   ├── base.py              # SQLAlchemy DeclarativeBase
│   │   ├── models.py            # Relational models & constraints
│   │   └── session.py           # Engine & SessionLocal factory
│   ├── ingestion/               # Extraction & file readers
│   │   ├── readers.py           # Safe CSV reader & hash computation
│   │   └── source_adapters.py   # Schema detection & column mapping
│   ├── pipelines/               # Pipeline orchestration
│   │   └── orchestrator.py      # 5-stage ETL & Reconciliation runner
│   ├── quality/                 # Data quality engine
│   │   ├── rules.py             # Rule definitions & check functions
│   │   └── validation.py        # Record & batch validation logic
│   ├── reconciliation/          # Financial reconciliation engine
│   │   └── matcher.py           # Exact decimal matching & classification
│   ├── schemas/                 # Pydantic request & response models
│   └── transformations/         # Data normalization
│       └── normalize.py         # Dates, decimals, currencies, text
├── migrations/                  # Alembic database migrations
│   ├── versions/                # Versioned migration scripts
│   └── env.py                   # Migration environment runner
├── scripts/
│   ├── generate_sample_data.py  # Realistic data generator with anomalies
│   └── run_pipeline.py          # CLI pipeline runner
├── tests/
│   ├── unit/                    # Unit tests (ingestion, dq, recon, transform)
│   └── integration/             # Integration tests (end-to-end, API)
├── .env.example                 # Environment variables template
├── .gitignore                   # Git ignore patterns
├── Dockerfile                   # Multi-stage Docker build
├── docker-compose.yml           # PostgreSQL, API, Dashboard orchestration
├── Makefile                     # Developer command runner
└── pyproject.toml               # Package configuration & dependencies
```

---

## ⚖️ License

Distributed under the MIT License. See `LICENSE` for more information.
