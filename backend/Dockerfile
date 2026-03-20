# ============================================================
# Backend Dockerfile
# Stages: deps → development | production
#
# Layer-cache strategy:
#   1. Install uv (rarely changes)
#   2. Copy only pyproject.toml + uv.lock → install deps
#      (this layer is only busted when deps change)
#   3. Copy source code last
#      (source changes never re-trigger dep install)
# ============================================================

# ---- Stage 1: install dependencies -------------------------
FROM python:3.12-slim AS deps

# Install uv (fast, reproducible installs from uv.lock)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# System deps needed to compile some packages (e.g. cryptography, asyncpg)
# poppler-utils provides pdftotext; qpdf provides page splitting
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    qpdf \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifest + lockfile.
# Source code changes will NOT bust this layer.
COPY pyproject.toml uv.lock ./

# Install all deps (including [dev] extras) into the system python.
# We include the project itself here; the editable reinstall in stage 2
# will replace it so hot-reload works correctly.
RUN uv pip install --system ".[dev]"

# ---- Stage 2: development ----------------------------------
FROM deps AS development

# Now copy source — only this layer and below are busted on code changes.
COPY . .

# Reinstall the project itself as editable so imports work with hot-reload.
RUN uv pip install --system -e .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- Stage 3: production -----------------------------------
FROM python:3.12-slim AS production

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Minimal runtime system dep (libpq for asyncpg, poppler-utils for pdftotext, qpdf for page splitting)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    poppler-utils \
    qpdf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install production deps (no [dev] extras)
COPY pyproject.toml uv.lock ./
RUN uv pip install --system .

# Copy source and install project package
COPY . .
RUN uv pip install --system -e .

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--access-log"]
