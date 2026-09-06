# LOATS13July2026 - Deployment Guide

**L**atency-**O**ptimized **A**lgorithmic **T**rading **S**ystem **13July2026**

> **LITE Philosophy**: No Docker services, no heavy ML, pure Python.
> Single-file SQLite database, JSONL audit logs, zero external dependencies.

---

## Table of Contents

1. [Deployment Overview](#deployment-overview)
2. [Development Setup](#development-setup)
3. [Docker Deployment](#docker-deployment)
4. [Production Deployment](#production-deployment)
5. [Health Checks](#health-checks)
6. [Troubleshooting](#troubleshooting)

---

## Deployment Overview

LOATS13July2026 is designed as a lightweight, single-process application that:
- Connects to OpenAlgo REST API for ANALYZE mode operations
- Uses SQLite WAL mode for local data persistence
- Stores JSONL audit logs for compliance (7-year retention)
- Requires no external services (no PostgreSQL, Redis, etc.)

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.12 | 3.12 |
| RAM | 512 MB | 1 GB |
| Disk | 1 GB | 5 GB |
| OS | Windows 10+ / Ubuntu 20.04+ / macOS 12+ | Windows 11 / Ubuntu 22.04+ |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LOATS13July2026                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │Sentiment│  │ Technical│ │ Strength│  │  Rules  │         │
│  │Analysis │  │Analysis │  │Calculator│  │ Engine  │         │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘         │
│       └────────────┴────────────┴────────────┘              │
│                         │                                     │
│                    ┌────▼────┐                               │
│                    │Orchestr.│                               │
│                    └────┬────┘                               │
│                         │                                     │
│  ┌──────────────────────┼──────────────────────┐           │
│  │                  Risk Manager               │           │
│  └──────────────────────┼──────────────────────┘           │
│                         │                                     │
│              ┌───────────▼───────────┐                       │
│              │   OpenAlgo Adapter   │                       │
│              └───────────┬───────────┘                       │
└──────────────────────────┼───────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   OpenAlgo REST API   │
              │   (ANALYZE mode)      │
              └────────────────────────┘
```

---

## Development Setup

### Prerequisites

- Python 3.12+
- Git
- OpenAlgo API key

### Installation

```powershell
# Clone the repository
git clone https://github.com/npmvlKP/LOATS13July2026.git
cd LOATS13July2026

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Create .env file
cp .env.example .env
# Edit .env with your OpenAlgo credentials
```

### Environment Variables

Create a `.env` file in the project root:

```env
# OpenAlgo Configuration
OPENALGO_API_KEY=your_openalgo_api_key_here
OPENALGO_BASE_URL=http://127.0.0.1:5000
OPENALGO_MODE=ANALYZE

# Application Settings
LOG_LEVEL=INFO
TZ=Asia/Kolkata

# Optional: Telegram Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### Running the Application

```powershell
# Run quick health check
python quick_health_check.py

# Run full project health check
python verify_project_health.py

# Run tests
pytest tests/ --cov=src --cov-branch --cov-fail-under=80

# Run the main application (if main.py exists)
python -m src.loats.main
```

---

## Docker Deployment

### Quick Start

```bash
# Build the Docker image
docker build -t loats13july2026:latest .

# Run with environment file
docker run -d \
  --name loats13july2026 \
  --env-file .env \
  -p 8000:8000 \
  loats13july2026:latest

# Check logs
docker logs loats13july2026

# Run health check
docker exec loats13july2026 python quick_health_check.py
```

### Using Docker Compose

```bash
# Development environment
docker compose --profile dev up -d

# Test environment
docker compose --profile test up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### Docker Security Features

The Docker deployment includes:
- Read-only root filesystem
- Non-root user execution (optional, uncomment in Dockerfile)
- Resource limits (CPU/memory)
- Health checks
- No new privileges

---

## Production Deployment

> **IMPORTANT**: For production deployments, use cloud-native services instead of Docker.

### Cloud Platform Recommendations

| Provider | Recommended Services |
|----------|---------------------|
| AWS | Lambda + CloudWatch, or ECS Fargate |
| GCP | Cloud Run, or GKE |
| Azure | Container Apps, or AKS |
| Railway | Simple Python deployment |

### Production Checklist

- [ ] Set `LOG_LEVEL=INFO` or `LOG_LEVEL=WARNING`
- [ ] Configure secure API key storage (AWS Secrets Manager, etc.)
- [ ] Set up monitoring (CloudWatch, DataDog, etc.)
- [ ] Enable structured JSON logging
- [ ] Configure log rotation (handled by structlog)
- [ ] Set up alerts for errors
- [ ] Enable audit log retention (7 years for SEBI compliance)
- [ ] Configure TLS/HTTPS
- [ ] Set up rate limiting
- [ ] Enable backup for SQLite database

### systemd Service (Linux)

Create `/etc/systemd/system/loats.service`:

```ini
[Unit]
Description=LOATS13July2026 - LITE OpenAlgo Trading System
After=network.target

[Service]
Type=simple
User=loats
WorkingDirectory=/opt/loats
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/opt/loats/.env
ExecStart=/opt/loats/.venv/bin/python -m src.loats.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable loats
sudo systemctl start loats
sudo systemctl status loats
```

---

## Health Checks

### Quick Health Check

```bash
python quick_health_check.py
```

Expected output:
```
ROCKET LOATS13July2026 Quick Health Check
==================================================
CHECK Virtual Environment... PASS
CHECK Python Version... PASS
CHECK Critical Imports... PASS
CHECK Model Tests... PASS
CHECK Options Tests... PASS
CHECK Type Safety... PASS
CHECK Code Quality... PASS
CHECK Security... PASS

==================================================
Quick Health Check Results: 8/8 checks passed (100.0%)
PROJECT HEALTH: HEALTHY
```

### Full Health Check

```bash
python verify_project_health.py
```

### Docker Health Check

```bash
docker inspect --format='{{.State.Health.Status}}' loats13july2026
```

### Kubernetes Health Check

```bash
kubectl get pods -l app=loats13july2026
kubectl describe pod -l app=loats13july2026
```

---

## Troubleshooting

### Common Issues

#### Import Errors

```bash
# Ensure you're in the virtual environment
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate    # Windows

# Reinstall dependencies
pip install -e ".[dev]"
```

#### Type Check Failures

```bash
# Run mypy with specific config
mypy src/ --strict --config-file pyproject.toml

# Check for missing type stubs
pip install pydantic>=2.10.0 pydantic-settings>=2.7.0
```

#### Test Failures

```bash
# Run tests with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_models.py -v

# Run with coverage
pytest tests/ --cov=src --cov-branch
```

#### Docker Build Failures

```bash
# Clean Docker cache
docker builder prune -a

# Rebuild without cache
docker build --no-cache -t loats13july2026:latest .

# Check Docker logs
docker logs loats13july2026
```

#### Secrets Detected by Gitleaks

If gitleaks reports secrets, follow these steps:

1. Remove the secret from the file
2. Run `git filter-branch` to rewrite history (if committed)
3. Use environment variables or secrets management
4. Re-commit with the secret removed

### Log Locations

| Environment | Log Location |
|-------------|--------------|
| Development | `./logs/` directory |
| Docker | `docker logs loats13july2026` |
| Production | System journal or cloud logging |
| systemd | `journalctl -u loats` |

### Monitoring Endpoints

Configure your monitoring to watch:
- Exit codes (0 = healthy, non-zero = error)
- Log files for ERROR/CRITICAL levels
- SQLite database file size
- JSONL audit log growth

---

## CI/CD Validation Commands

Run these commands to validate the deployment:

```bash
# Quality Gates
ruff check src/ tests/ --config pyproject.toml
ruff format --check src/ tests/ --config pyproject.toml
black --check src/ tests/ --config pyproject.toml
isort --check-only src/ tests/ --settings-path pyproject.toml
mypy src/ --strict --config-file pyproject.toml
bandit -r src/ -c pyproject.toml

# Tests
pytest tests/ --cov=src --cov-branch --cov-fail-under=80

# Security
pip-audit
gitleaks detect --source . --config .gitleaks.toml --no-banner

# Health Check
python quick_health_check.py
python verify_project_health.py
```

---

## Compliance Notes

### SEBI Requirements

- **Audit Trail**: 7-year retention, SHA-256 chained logs
- **Decimal Finance**: No float for financial calculations
- **IST Timezone**: All datetime operations use Asia/Kolkata
- **ANALYZE Mode Only**: No live trading capabilities

### Security Best Practices

- Never commit API keys to repository
- Use environment variables for secrets
- Enable audit logging
- Regular security scans via GitHub Actions
- Keep dependencies updated

---

## Support

For issues and questions:
1. Check this deployment guide
2. Review health check output
3. Check application logs
4. Review GitHub Issues

---

**Version**: 0.1.0  
**Last Updated**: 2026-07-21  
**Author**: npmvlKP