# LOATS13July2026 - LITE OpenAlgo Trading System
# LITE Philosophy: No Docker services, no heavy ML, pure Python
# This container is for CI/CD and optional local testing only

FROM python:3.12-slim

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Set timezone to IST for SEBI compliance
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Build args
ARG BUILD_VERSION=0.1.0
ARG BUILD_DATE

# Labels
LABEL maintainer="npmvlKP@gmail.com"
LABEL version="${BUILD_VERSION}"
LABEL description="LITE OpenAlgo Trading System - Options Analysis Platform"
LABEL io.openshift.expose-services=""

# Set working directory
WORKDIR /app

# Install system dependencies for Python packages
# LITE: No Redis, no Prometheus, minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better layer caching
# (README.md is a build input: pyproject.toml references it via `readme`)
COPY requirements-core.txt .
COPY pyproject.toml .
COPY README.md .

# Install Python dependencies
# LITE: No PyTorch, no heavy ML models, no QuantLib, no PostgreSQL
# Using pure Python alternatives for Windows compatibility
RUN pip install --no-cache-dir -r requirements-core.txt

# Copy project source
COPY src/ ./src/

# Install the package in production mode (not editable)
RUN pip install --no-cache-dir --no-deps .

# Copy the packaged health-check suite (the root-level quick_health_check.py /
# verify_project_health.py were removed by the F8-M-05 repo cleanup wave; the
# maintained checks live under scripts/ and ship with the repo)
COPY scripts/fr7_health_check.py ./scripts/

# Create non-root user for security
RUN addgroup --system --gid 1001 loats && \
    adduser --system --uid 1001 --ingroup loats loats && \
    chown -R loats:loats /app
USER loats

# Health check: HC-01 is a pure structural check (packaged tree intact,
# src/__init__.py mypy-collision breaker absent) with no network or credentials
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python scripts/fr7_health_check.py --only HC-01 >/dev/null 2>&1; exit $?

# Default command runs the structural health check on container start (for CI/CD)
# For runtime, use: CMD ["python", "-m", "loats.main"]
CMD ["python", "scripts/fr7_health_check.py", "--only", "HC-01"]
