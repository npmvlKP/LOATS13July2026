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

- **Evidence-Based Compliance Posture**: applicability assessment with
  per-requirement controls, evidence, owners, and gaps in
  [docs/COMPLIANCE-MATRIX.md](docs/COMPLIANCE-MATRIX.md) (paper-trading
  system; SEBI/NSE live-path obligations are operator/broker-owned; no
  NIST/ISO certification claimed)
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

No regulator- or certification-facing compliance determination is claimed
by this repository. The evidence-based posture lives in
[docs/COMPLIANCE-MATRIX.md](docs/COMPLIANCE-MATRIX.md): applicability
assessment first (paper-trading system; the SEBI/NSE live order-path
obligations — registration, static IP, API keys, algo-ID tagging — are
operator/broker-owned and open until live trading is ever enabled), then
per-requirement matrices for the SEBI/NSE retail-algo framework
(SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013; NSE INVG/67858), selected
NIST SP 800-53 families, and the ISO 27001 posture, each with control,
evidence, owner, and gap. In-repo design controls that are evidenced today:

- **OPS cap ≤ 3/s**: shared `RateLimiter`, `max_ops=3` below the SEBI/NSE
  10-OPS threshold with headroom; regression nets HC-14/F6-C-01.
- **Kill switch**: emergency halt primitive with a live drill record
  (01Oct2026, 122 blocked cycles audited) and fail-closed refusal.
- **Audit Trail**: 7-year retention default (`retention_days=2555`),
  append-only, SHA-256-chained (`src/loats/database.py`).
- **Decimal-only finance**: Decimal fields with 0.01 quantization
  validators; **IST-aware datetime** (`Asia/Kolkata`).

## License

MIT License
