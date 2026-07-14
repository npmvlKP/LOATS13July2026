# LOATS13July2026

**L**atency-**O**ptimized **A**lgorithmic **T**rading **S**ystem for **13July2026** Expiry

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

Designed for **ANALYZE mode only** with OpenAlgo REST API integration.

## Key Features

- **Strict Compliance**: SEBI algo regulations + NIST SP 800-53 + ISO 27001:2022
- **Latency Optimized**: Strike <5ms, trail <1ms, orchestrator cycle <100ms
- **Rate Limited**: Conservative NVIDIA NIM API usage (≤20 req/min, ≥3s gap)
- **Type Safe**: Full mypy --strict compliance
- **Security Focused**: Bandit, gitleaks, and comprehensive security scanning
- **Test Coverage**: ≥80% branch coverage with pytest

## Project Structure

```
src/loats/
├── sentiment/      # Sentiment analysis (VADER)
├── ta_va/          # Technical and volume analysis
├── strength/       # Strength calculation
├── rules/          # Rule-based decision engine
├── strike/         # Strike selection logic
├── risk/           # Risk management
├── orchestrator/   # Pipeline orchestration
├── adapters/       # OpenAlgo adapter pattern
├── config/         # Configuration management
├── models/         # Data models
└── utils/          # Utility functions (including NIM rate guard)
```

## Setup Instructions

### Prerequisites

- Python 3.12+
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

### Quality Gates

Run all quality gates:

```powershell
# Lint and format
ruff check src/ tests/ --config pyproject.toml
ruff format --check src/ tests/ --config pyproject.toml

# Type checking
mypy src/ --strict --config-file pyproject.toml

# Security scanning
bandit -r src/ -c pyproject.toml -q

# Secret scanning
gitleaks detect --source . --config .gitleaks.toml --no-banner

# Run tests
pytest tests/unit/ tests/integration/ -v --cov=src --cov-branch --cov-fail-under=80 -x
```

## Development Principles

1. **Stability > Security > Data Integrity > Performance**
2. **No 500ms resting time** (SEBI 2018 dropped it)
3. **Decimal-only finance** (No float in financial calculations)
4. **IST-aware datetime** (No naive datetime)
5. **Structured logging** (No print statements in src/)
6. **Function size ≤100 LOC**
7. **≤3 OPS** (Self-imposed below SEBI/NSE 10 OPS threshold)

## Compliance

- **SEBI Algo Regulations**: Full compliance with Indian algorithmic trading regulations
- **NIST SP 800-53**: Security and privacy controls
- **ISO 27001:2022**: Information security management
- **Audit Trail**: 7-year retention, append-only, SHA-256 chained

## License

MIT License
