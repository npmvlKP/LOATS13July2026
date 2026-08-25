# LOATS13July2026 Runbook & Monitoring Guide

## Overview

LOATS13July2026 (LITE OpenAlgo Trading System) is a latency-optimized algorithmic trading system with real-time alerts, risk controls, and SEBI compliance features.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Deployment](#deployment)
3. [Monitoring](#monitoring)
4. [Alerting](#alerting)
5. [Troubleshooting](#troubleshooting)
6. [Emergency Procedures](#emergency-procedures)
7. [Health Checks](#health-checks)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOATS13July2026 System                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Scheduler  │  │   Alerts    │  │    Trading Engine       │  │
│  │  (APScheduler│  │  (Telegram) │  │   (OpenAlgo Client)     │  │
│  │   + IST)    │  │             │  │                         │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
│         │                │                     │                │
│  ┌──────▼────────────────▼─────────────────────▼─────────────┐  │
│  │                    Database Layer                        │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │  │
│  │  │   SQLite   │  │    WAL     │  │   Audit Trail       │ │  │
│  │  │   (WAL)    │  │   Mode     │  │   (SHA-256 Logs)    │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Deployment

### Docker Deployment

```bash
# Build and run
docker build -t loats:latest .
docker run -d --name loats \
  -e OPENALGO_API_KEY=your_api_key \
  -e TELEGRAM_BOT_TOKEN=your_bot_token \
  -e TELEGRAM_CHAT_ID=your_chat_id \
  -e TELEGRAM_ADMIN_IDS=admin_id1,admin_id2 \
  loats:latest
```

### Docker Compose (Production)

```bash
# Start with full stack
docker-compose up -d

# Check status
docker-compose ps
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENALGO_API_KEY` | Yes | OpenAlgo API authentication key |
| `OPENALGO_BASE_URL` | No | OpenAlgo API URL (default: https://openalgo.sh/api/v2) |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token for alerts |
| `TELEGRAM_CHAT_ID` | No | Telegram chat ID for alerts |
| `TELEGRAM_ADMIN_IDS` | No | Comma-separated admin user IDs |
| `DEFAULT_SYMBOL` | No | Default trading symbol |
| `ENVIRONMENT` | No | "development" or "production" |
| `LOG_LEVEL` | No | Logging level (default: INFO) |

---

## Monitoring

### Health Check Endpoint

```bash
# Check system health
curl http://localhost:8000/health
```

### Circuit Breaker Status

The system implements circuit breakers for:
- **OpenAlgo API**: Protects against external API failures
- **Telegram**: Ensures alerts don't block trading

Check status via Telegram commands:
```
/status
```

### Key Metrics to Monitor

| Metric | Threshold | Action |
|--------|-----------|--------|
| Circuit Breaker Open (OpenAlgo) | > 0 | Check OpenAlgo API status |
| Circuit Breaker Open (Telegram) | > 0 | Check network/bot token |
| Database Size | > 500MB | Run vacuum cleanup |
| Failed Orders | > 5% | Review order logic |
| Kill Switch Active | True | Verify intentional activation |

---

## Alerting

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Show welcome message and help |
| `/status` | Show system status and kill switch state |
| `/kill <reason>` | Activate kill switch (admin only) |
| `/resume <reason>` | Deactivate kill switch (admin only) |
| `/positions` | View current positions |
| `/orders` | View open orders |
| `/signals` | View recent trading signals |
| `/help` | Show help message |

### Alert Types

| Type | Icon | Trigger |
|------|------|---------|
| INFO | ℹ️ | Routine events |
| WARNING | ⚠️ | Attention needed |
| ERROR | 🚨 | Issues requiring action |
| SUCCESS | ✅ | Successful operations |

### Alert Cooldown

Alerts have a 5-minute cooldown period to prevent spam.

---

## Troubleshooting

### Common Issues

#### 1. Circuit Breaker Open

**Symptom**: OpenAlgo API calls failing, "circuit breaker open" in logs

**Resolution**:
1. Check OpenAlgo API status: https://status.openalgo.in
2. Verify API credentials
3. Wait for recovery (auto-reset after failure window)

#### 2. Telegram Not Receiving Alerts

**Symptom**: Commands not responding, no alerts received

**Resolution**:
1. Verify bot token is correct
2. Check bot has been started by user
3. Verify chat ID is correct
4. Check network connectivity

#### 3. Database Locked Errors

**Symptom**: "database is locked" errors in logs

**Resolution**:
1. Ensure only one instance running
2. On Windows: Check for orphaned processes
3. Restart the application

#### 4. Market Hours Not Detected Correctly

**Symptom**: Scans running at wrong times

**Resolution**:
1. Verify system timezone (IST for NSE/BSE)
2. Check market holiday calendar
3. Verify NTP time synchronization

### Log Locations

| Environment | Log Location |
|-------------|-------------|
| Development | Console output |
| Production | `./logs/` directory |

### Log Analysis

```bash
# View recent errors
tail -f logs/loats.log | grep ERROR

# Search for specific symbol
grep "RELIANCE" logs/loats.log

# View audit trail
grep "AUDIT" logs/loats.log
```

---

## Emergency Procedures

### Kill Switch Activation

**When to Use**:
- Unexpected market conditions
- System malfunction
- Security breach
- Manual intervention required

**Activation**:
1. Send `/kill <reason>` via Telegram
2. Or: Set `KILL_SWITCH_ACTIVE=true` in environment
3. Or: Call `alerts.activate_kill_switch()` programmatically

**What Happens**:
1. Kill switch flag set to True
2. All open orders cancelled
3. New order placement blocked
4. Alert sent via Telegram

### System Recovery

1. Resolve underlying issue
2. Send `/resume <reason>` via Telegram
3. Verify orders are not being placed automatically
4. Resume normal operation

### Graceful Shutdown

```bash
# Send SIGTERM
docker stop loats

# Or send SIGINT
docker kill --signal=SIGINT loats
```

### Hard Shutdown (Last Resort)

```bash
# Force stop
docker kill loats
```

**Warning**: May leave database in inconsistent state. Run integrity check after.

---

## Health Checks

### Pre-Deployment Checklist

- [ ] Environment variables configured
- [ ] OpenAlgo API accessible
- [ ] Telegram bot configured (if alerts enabled)
- [ ] Database initialized
- [ ] Logs directory writable
- [ ] Timezone correct (IST for India markets)

### Startup Verification

1. Check startup logs for "Trading system initialized successfully"
2. Verify scheduler jobs registered
3. Test Telegram bot with `/status` command
4. Place test order to verify API connectivity

### Daily Health Check

1. Review error logs for patterns
2. Check circuit breaker states
3. Verify Telegram alerts being received
4. Monitor order fill rates
5. Review position limits

### Weekly Maintenance

1. Run database vacuum
2. Review audit log integrity
3. Check disk space
4. Review backup procedures
5. Update dependencies if needed

---

## Runbook Version

- **Version**: 1.0.0
- **Last Updated**: 2026-07-21
- **System**: LOATS13July2026

## Support

For issues, contact the development team or review logs in `./logs/`.