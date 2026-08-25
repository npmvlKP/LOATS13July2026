# Value-at-Risk (VaR) Engine

## Overview

The VaR engine implements multiple approaches to Value-at-Risk calculation for comprehensive risk management:

1. Historical simulation
2. Parametric (normal distribution)
3. Monte Carlo simulation

## Key Features

- **Multi-asset support**: Handles equities, fixed income, and derivatives
- **Comprehensive reporting**: Provides VaR, expected shortfall, delta, and CVaR
- **CMP-compliant interfaces**: Integrates with Compliance Monitoring Program
- **Statistical rigour**: Features conditional VaR and fat tail adjustments

## Basic Usage

### Initialize Engine

```python
engine = VaREngine(
    confidence_level=0.99,  # 99% confidence
    window_size=252         # One year of trading days
)
```

### Historical Simulation

```python
# For standalone asset
historical_result = engine.historical_standalone(
    prices,                     # Historical price series
    Decimal('1,000,000'),      # Asset value
    days=10                    # 10-day holding period
)
```

### Parametric VaR

```python
parametric_result = engine.parametric_normal(
    prices,
    Decimal('1,000,000'),
    days=10,
    fat_tail_adj=1.2          # Adjust for fat tails
)
```

### Monte Carlo Simulation

```python
monte_carlo_result = engine.monte_carlo(
    current_price=Decimal('200'),
    value=Decimal('2,000,000'),
    days=7,
    samples=50_000
)
```

## Integration with CMP

```python
from src.cmp import CMPMonitor

monitor = CMPMonitor()
results = monitor.evaluate_risk(
    {
        "var_method": "historical_standalone",
        "parameters": {
            "prices": [...],
            "value": Decimal('1,000,000'),
            "days": 10
        }
    }
)
```

## Implementation Notes

- All values use `decimal.Decimal` for financial precision
- Methods validate input ranges and sizes
- Asia/Kolkata timezone used internally
- Follows SEBI requirements for VaR calculation

## Compliance Considerations

- Risk limits: ΔVaR ≤ 30% for individual assets
- Holding periods must be ≥ 1 day
- Confidence levels: 95-99% recommended

## Advanced Usage

### Portfolio Risk

```python
portfolio_result = engine.historical_portfolio({
    "AAPL": (Decimal('100'), 150.25),
    "GOOG": (Decimal('50'), 2600.75)
})
```

### Risk Contribution
```python
result = engine.parametric_normal(
    ...,
    risk_contribution=True
)
```

## Performance

| Method           | Recommended Samples | O(Complexity) |
|------------------|---------------------|---------------|
| Historical       | N/A                 | O(n log n)    |
| Parametric       | N/A                 | O(n)          |
| Monte Carlo      | 10K-100K            | O(m)          |