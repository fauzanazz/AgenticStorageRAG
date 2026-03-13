FROM python:3.12-slim AS base

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy full source first (needed for editable install with hatchling)
COPY pyproject.toml ./
COPY app/ ./app/

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Copy remaining files (alembic, scripts, etc.)
COPY . .

# --- Development target ---
FROM base AS development
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- Production target ---
FROM python:3.12-slim AS production

WORKDIR /app

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# System dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy full source (needed for editable install)
COPY pyproject.toml ./
COPY app/ ./app/

# Install only production dependencies
RUN pip install --no-cache-dir -e .

# Copy remaining files
COPY . .

# Own files as non-root user
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--access-log"]
