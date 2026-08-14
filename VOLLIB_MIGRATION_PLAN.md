# Vollib Migration Plan

## Current State Analysis

### Vollib Usage in Codebase

The project currently uses `vollib` for Black-Scholes option pricing calculations:

**Files using vollib:**
- `src/loats/options.py` - Main options analysis module
- `tests/test_options.py` - Test file for options functionality
- `tests/test_options_coverage.py` - Coverage tests for options

**Specific imports:**
```python
from vollib.black_scholes import black_scholes
from vollib.black_scholes.greeks.analytical import delta, gamma, rho, theta, vega
from vollib.black_scholes.implied_volatility import implied_volatility
```

### Issues with Current Implementation

1. **Deprecation**: `vollib` has been deprecated since 2026-07-15
2. **Fallback Logic**: Current code has extensive fallback logic for when vollib fails
3. **Performance**: External dependency adds overhead
4. **Maintenance**: Deprecated packages may not receive security updates

## Migration Options

### Option 1: py_vollib (Recommended)

**Pros:**
- Direct successor to vollib
- Maintained and actively developed
- API compatibility with vollib
- Minimal code changes required

**Cons:**
- Still an external dependency
- May have similar deprecation risks in future

**Implementation:**
```python
# Replace imports
from py_vollib.black_scholes import black_scholes
from py_vollib.black_scholes.greeks import delta, gamma, rho, theta, vega
from py_vollib.black_scholes.implied_volatility import implied_volatility
```

### Option 2: QuantLib

**Pros:**
- Industry-standard quantitative finance library
- Comprehensive financial mathematics support
- Actively maintained
- High performance

**Cons:**
- Steeper learning curve
- More complex API
- Larger dependency
- Significant code changes required

**Implementation:**
```python
import QuantLib as ql

# Would require complete rewrite of options calculations
```

### Option 3: Hand-roll Black-Scholes (~200 LOC) (Recommended for Long-term)

**Pros:**
- Zero external dependencies
- Full control over implementation
- Customizable for specific needs
- Better performance optimization
- No deprecation risks

**Cons:**
- Development time (~4-8 hours)
- Testing overhead
- Maintenance responsibility

## Recommended Migration Path

### Phase 1: Immediate Fix (1-2 hours)
- Replace `vollib` with `py_vollib` as direct drop-in replacement
- Update requirements.txt
- Run full test suite to ensure compatibility
- Remove fallback logic that was handling vollib failures

### Phase 2: Long-term Solution (4-8 hours)
- Implement custom Black-Scholes functions in `src/loats/options_math.py`
- Add comprehensive unit tests with known values
- Benchmark against py_vollib for accuracy
- Gradually replace py_vollib calls with custom implementation
- Remove py_vollib dependency

## Implementation Details

### Custom Black-Scholes Implementation

```python
# src/loats/options_math.py
import math
from decimal import Decimal
from typing import Literal

def black_scholes(
    flag: Literal["c", "p"],
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float
) -> float:
    """
    Black-Scholes option pricing formula.

    Args:
        flag: 'c' for call, 'p' for put
        S: Underlying asset price
        K: Strike price
        t: Time to expiration (in years)
        r: Risk-free interest rate
        sigma: Volatility

    Returns:
        Option price
    """
    # Implementation using standard Black-Scholes formula
    # ... (full implementation)
    pass

def black_scholes_greeks(
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float
) -> dict:
    """
    Calculate all Black-Scholes Greeks.

    Returns:
        dict with keys: delta, gamma, theta, vega, rho
    """
    # Implementation of Greek calculations
    # ... (full implementation)
    pass

def implied_volatility(
    flag: Literal["c", "p"],
    S: float,
    K: float,
    t: float,
    r: float,
    price: float
) -> float:
    """
    Calculate implied volatility using Newton-Raphson method.

    Args:
        flag: 'c' for call, 'p' for put
        S: Underlying asset price
        K: Strike price
        t: Time to expiration (in years)
        r: Risk-free interest rate
        price: Market price of option

    Returns:
        Implied volatility
    """
    # Implementation using numerical methods
    # ... (full implementation)
    pass
```

### Testing Strategy

1. **Unit Tests**: Test each function with known analytical solutions
2. **Regression Tests**: Ensure new implementation matches vollib/py_vollib results within acceptable tolerance
3. **Edge Cases**: Test with extreme values, zero volatility, etc.
4. **Performance Tests**: Benchmark against current implementation

## Timeline

- **Week 1**: Research and decide on migration path
- **Week 2**: Implement Phase 1 (py_vollib replacement)
- **Week 3-4**: Implement Phase 2 (custom implementation)
- **Week 5**: Full testing and validation

## Risk Assessment

- **Low Risk**: py_vollib migration (direct replacement)
- **Medium Risk**: Custom implementation (requires thorough testing)
- **High Risk**: QuantLib migration (complex API changes)

## Recommendation

**Short-term**: Migrate to `py_vollib` immediately to resolve deprecation warnings
**Long-term**: Implement custom Black-Scholes functions for zero-dependency solution

This approach provides immediate relief from deprecation warnings while setting up a sustainable long-term solution.