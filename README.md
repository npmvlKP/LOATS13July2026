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
- **Test Coverage**: 88.74% branch coverage with pytest (1805 tests passing;
  per-module floors enforced by `scripts/check_per_module_coverage.py`)

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

**CMP posture (S-19, `docs/CMP-SUPERSESSION-REGISTER.md`):** Docker in this
repository is **CI-only**. The CMP LITE mandate is pip-only, no Docker, and
no compose file is sanctioned for live deployment — including
`docker-compose.prod.yml`. The three Docker variants exist only to build
and smoke-test the image in CI. Live deployment is the bare-metal pip path
(`docs/DEPLOY.md`, systemd unit included). A bare `docker run` of the image
executes the HC-01 structural health probe and exits; the engine
(`python -m loats.main`) starts only via the compose `command:` overrides,
which remain CI-only evidence.

The three variants:

1. **CI/CD Testing**: `docker-compose.yml`
   - Runs the packaged HC-01 health probe on startup (`Dockerfile` CMD)
   - Includes development volume mounts for hot-reload
   - For testing and validation only

2. **CI-only prod-compose variant**: `docker-compose.prod.yml`
   - Overrides the CMD to `python -m loats.main`, but the file is NOT a
     sanctioned live deployment path (CMP LITE mandate; S-19 in
     `docs/CMP-SUPERSESSION-REGISTER.md`)
   - Health check: `curl http://localhost:8001/` (metrics endpoint)
   - Higher resource limits (2 CPU, 1GB RAM)

3. **Development Runtime**: `docker-compose.runtime.yml`
   - Overrides the CMD to `python -m loats.main` with development features
   - CI-only posture (S-19): not a live deployment path

**Usage:**

```powershell
# For CI/CD testing
docker compose -f docker-compose.yml up

# CI-only variant - NOT for live deployment (CMP LITE mandate, see S-19)
docker compose -f docker-compose.prod.yml up -d

# For development runtime
docker compose -f docker-compose.runtime.yml up
```

**Important:**
- The default `Dockerfile` CMD is the HC-01 structural health probe
  (`scripts/fr7_health_check.py --only HC-01`) for CI/CD purposes;
  `quick_health_check.py` does not exist in this tree
- `docker-compose.prod.yml` / `docker-compose.runtime.yml` override the
  command to the engine (`python -m loats.main`); Docker stays CI-only
  under the CMP LITE mandate (S-19) — live deployment is the pip path in
  `docs/DEPLOY.md`
- A bare `docker run` of the image runs the HC-01 probe and exits; only
  the compose overrides start the engine
- Metrics endpoint is available at `http://localhost:8001/`

### Quality Gates

Run all quality gates:

```powershell
# Linting and formatting (same scope as the CI ruff jobs)
ruff check src/ tests/ scripts/ --config pyproject.toml
ruff format --check src/ tests/ scripts/ --config pyproject.toml

# Type checking
mypy src/ --strict --config-file pyproject.toml

# Security scanning
bandit -r src/ -c pyproject.toml

# Secret scanning
gitleaks detect --source . --config .gitleaks.toml --no-banner

# Dependency audit (the --ignore-vuln waiver is ADR-0010: nltk is a
# dev-toolchain transitive of safety, no runtime import -- remove the
# flag the day nltk 3.11 or a safety release without nltk lands)
pip-audit --format=json --output pip-audit-report.json --ignore-vuln PYSEC-2026-3740

# Run tests with coverage, then enforce the per-module floors
pytest tests/ --cov=src --cov-branch --cov-fail-under=80 --cov-report=json:coverage.json
python scripts/check_per_module_coverage.py
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
  grades it (≥14-day span, zero unhandled exceptions, routing enabled,
  **and measured decisional activity — zero routing counters is a hard
  FAIL per ADR-006 Amendment 2**). Every routed decision leaves a
  SHA-256-chained `ROUTE` audit row carrying the routing outcome
  (success / disabled / error).

## License

MIT License
