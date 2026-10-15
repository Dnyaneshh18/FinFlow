.PHONY: help install dev generate-data run-pipeline api dashboard test lint format clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install .

dev: ## Install all dependencies (including dev)
	pip install ".[dev]"

generate-data: ## Generate sample synthetic data
	python scripts/generate_sample_data.py

run-pipeline: ## Run the ETL pipeline with sample data
	python scripts/run_pipeline.py

run-pipeline-full: ## Generate data then run pipeline
	python scripts/run_pipeline.py --generate

api: ## Start the FastAPI server
	uvicorn finflow.api.app:app --host 0.0.0.0 --port 8000 --reload

dashboard: ## Start the Streamlit dashboard
	streamlit run finflow/dashboard/app.py --server.port 8501

test: ## Run all tests
	pytest -v --tb=short

test-unit: ## Run unit tests only
	pytest tests/unit/ -v --tb=short

test-integration: ## Run integration tests only
	pytest tests/integration/ -v --tb=short

test-cov: ## Run tests with coverage
	pytest --cov=finflow --cov-report=term-missing --cov-report=html -v

lint: ## Run Ruff linter
	ruff check .

format: ## Format code with Ruff
	ruff format .

migrate: ## Run database migrations
	alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create msg="description")
	alembic revision --autogenerate -m "$(msg)"

clean: ## Remove generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
	rm -f finflow.db test_finflow.db
