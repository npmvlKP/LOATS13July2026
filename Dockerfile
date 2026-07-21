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
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better layer caching
COPY requirements-core.txt .
COPY pyproject.toml .

# Install Python dependencies
# LITE: No PyTorch, no heavy ML models, no QuantLib, no PostgreSQL
# Using pure Python alternatives for Windows compatibility
RUN pip install --no-cache-dir -r requirements-core.txt

# Install the package in editable mode with dev dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Copy project source
COPY src/ ./src/

# Copy scripts (health checks, etc.)
COPY quick_health_check.py verify_project_health.py ./

# Create non-root user for security (optional - uncomment if needed)
# RUN addgroup --system --gid 1001 loats && \
#     adduser --system --uid 1001 --ingroup loats loats && \
#     chown -R loats:loats /app
# USER loats

# Health check using the project's quick health check script
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python quick_health_check.py >/dev/null 2>&1; exit $?

# Default command runs quick health check on container start
CMD ["python", "quick_health_check.py"]