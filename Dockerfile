FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"

# Copy application
COPY . .

# Create data directories
RUN mkdir -p data/sample data/uploads

# Expose ports
EXPOSE 8000 8501

# Default command
CMD ["uvicorn", "finflow.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
