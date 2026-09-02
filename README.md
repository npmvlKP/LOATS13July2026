# LOATS13July2026

**L**atency-**O**ptimized **A**lgorithmic **T**rading **S**ystem **13July2026** Expiry

Multi-factor, sentiment-driven, rule-based options analysis platform for OpenAlgo ANALYZE mode.

## Project Overview

LOATS13July2026 is a high-performance options analysis platform that combines:
- **Sentiment Analysis** (VADER)
- **Technical/Volume Analysis**
- **Strength Calculation**
- **Rule-Based Decision Engine**
- **Strike Selection**
- **Risk Management**
- **Orchestration Layer**

Designed for **ANALYZE mode only** via OpenAlgo REST API integration.

## Key Features

- **Strict Compliance**: SEBI algo regulations, NIST 800-53, ISO 27001:2022
- **Rate Limited**: Conservative NVIDIA NIM API usage (≤20 req/min, ≥3s gap)
- **Type Safe**: Full mypy --strict compliance
- **Security Focused**: Bandit, gitleaks, and comprehensive security scanning
- **Test Coverage**: 89.02% branch coverage with pytest (784/801 tests passing)

## Project Structure

```
src/loats/
├── config/             Configuration management
├── utils/              Utility functions (including NIM rate guard)
├── alerts.py           Alert management
├── database.py         Database interaction
├── initialization.py   Project initialization
├── logging.py          Logging configuration
├── main.py             Main entry point
├── models.py           Data models
├── openalgo.py         OpenAlgo adapter
├── options.py          Options pricing & Greeks
├── scheduler.py        Task scheduling
├── sentiment.py        Sentiment analysis
└── ta.py               Technical analysis
```

## Setup Instructions

### Prerequisites

- Python 3.12
- pip
- Git

### Installation

```powershell
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Configuration

Create a `.env` file in the project root:

```env
OPENALGO_API_KEY=your_openalgo_api_key
OPENALGO_BASE_URL=http://127.0.0.1:5000
OPENALGO_MODE=ANALYZE
```

### Docker Deployment

**Three Docker Compose configurations are available:**

1. **CI/CD Testing**: `docker-compose.yml`
   - Runs quick health check on startup
   - Includes development volume mounts for hot-reload
   - For testing and validation only
   - Health check: `python quick_health_check.py`

2. **Production Deployment**: `docker-compose.prod.yml`
   - Starts the actual trading system using `python -m loats.main`
   - No development mounts (production-ready)
   - For actual production deployment
   - Health check: `curl http://localhost:8001/` (metrics endpoint)
   - Higher resource limits (2 CPU, 1GB RAM)

3. **Development Runtime**: `docker-compose.runtime.yml`
   - Starts the trading system with development features
   - For development with runtime testing

**Usage:**

```powershell
# For CI/CD testing
docker compose -f docker-compose.yml up

# For production deployment (RECOMMENDED for live deployment)
docker compose -f docker-compose.prod.yml up -d

# For development runtime
docker compose -f docker-compose.runtime.yml up
```

**Important:**
- The default `Dockerfile` uses `quick_health_check.py` as CMD for CI/CD purposes
- For production deployment, use `docker-compose.prod.yml` which overrides the command
- Production deployment uses `python -m loats.main` as the entry point
- Metrics endpoint is available at `http://localhost:8001/`

### Quality Gates

Run all quality gates:

```powershell
# Linting and formatting
ruff check src/ tests/ --config pyproject.toml
ruff format --check src/ tests/ --config pyproject.toml

# Type checking
mypy src/ --strict --config-file pyproject.toml

# Security scanning
bandit -r src/ -c pyproject.toml

# Secret scanning
gitleaks detect --source . --config .gitleaks.toml --no-banner

# Run tests
pytest tests/ --cov=src --cov-branch --cov-fail-under=80
```

## Development Principles

1. **Stability, Security, Data Integrity, and Performance**
2. **No 500ms resting time** (SEBI 2018 dropped it)
3. **Decimal-only finance** (No float for financial calculations)
4. **IST-aware datetime** (No naive datetime)
5. **Structured logging** (No print statements in src/)
6. **Function size ≤100 LOC**
7. **≤3 OPS** (Self-imposed below SEBI/NSE 10 OPS threshold)

## Compliance

- **SEBI Algo Regulations**: Full compliance with Indian algorithmic trading regulations.
- **NIST 800-53**: Security and privacy controls.
- **ISO 27001:2022**: Information security management.
- **Audit Trail**: 7-year retention, append-only, SHA-256 chained.

## Known Deviations (CMP Phase Gates)

- **F8-H-01 / CMP P5 — Analyzer routing default OFF.** CMP P5 requires
  routing ALL TradeDecisions to Analyzer Mode; production ships
  `analyzer_routing_enabled=false` (the runtime kill path and the guard
  against the F7-H-01 default-on fabrication; enforced by HC-19 and the
  HC registry AST check). The deviation is recorded in
  [ADR-006](docs/ADR-006-analyzer-routing-p5.md). The closing step is
  runnable: `scripts/run_p5_forward_test.py --ack-live-endpoint` enables
  routing only for the supervised 2-week run (log to
  `reports/p5_forward_test_*.json`); `scripts/verify_p5_forward_test.py`
  grades it (≥14-day span, zero unhandled exceptions, routing enabled).
  Every routed decision leaves a SHA-256-chained `ROUTE` audit row
  carrying the routing outcome (success / disabled / error).

## License

MIT License
