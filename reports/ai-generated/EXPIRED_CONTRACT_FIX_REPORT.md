# Technical Debt Fix: M6 - Expired Contract Error Handling

**Date:** 2026-07-21  
**Task:** Fix negative time-to-expiry silently clamped (options.py:53,109,173,263,309)

## Summary

Successfully replaced silent clamping of negative time-to-expiry values with proper `ExpiredContractError` exception handling across all 5 locations in `src/loats/options.py`.

## Changes Made

### 1. Added ExpiredContractError Exception Class

```python
class ExpiredContractError(ValueError):
    """Raised when attempting to calculate Greeks for an expired option contract."""
    
    def __init__(self, message: str, symbol=None, expiry=None, time_to_expiry=None):
        super().__init__(message)
        self.symbol = symbol
        self.expiry = expiry
        self.time_to_expiry = time_to_expiry
```

### 2. Updated Methods to Raise ExpiredContractError

| Location | Method | Before | After |
|----------|--------|--------|-------|
| ~line 53 | `OptionsEngine.calculate_greeks()` | `t = max(t, 0.0001)` | `if t <= 0: raise ExpiredContractError(...)` |
| ~line 109 | `OptionsEngine.calculate_implied_volatility()` | `t = max(t, 0.0001)` | `if t <= 0: raise ExpiredContractError(...)` |
| ~line 173 | `OptionsEngine.calculate_black_scholes()` | `t = max(t, 0.0001)` | `if t <= 0: raise ExpiredContractError(...)` |
| ~line 263 | Standalone `calculate_greeks()` | `t = max(t, 0.0001)` | `if t <= 0: raise ExpiredContractError(...)` |
| ~line 309 | Standalone `calculate_implied_volatility()` | `t = max(t, 0.0001)` | `if t <= 0: raise ExpiredContractError(...)` |

### 3. Added Backward Compatibility

- `calculate_greeks()` now accepts `allow_expired=False` parameter
- When `allow_expired=True`, calculations proceed even for expired contracts
- Default is `allow_expired=False` (strict mode)

### 4. Exported Exception

Added `ExpiredContractError` to `__all__` exports in `options.py`.

### 5. Updated Tests

- `tests/test_options.py`: Updated `test_edge_cases()` to verify error behavior
- Added `test_expired_contract_error_attributes()` to verify exception attributes
- All 14 tests pass ✓

## Verification Results

```
tests/test_options.py::TestOptionsAnalysis::test_black_scholes_consistency PASSED
tests/test_options.py::TestOptionsAnalysis::test_calculate_option_metrics PASSED
tests/test_options.py::TestOptionsAnalysis::test_calculate_open_interest_analysis PASSED
tests/test_options.py::TestOptionsAnalysis::test_analyze_option_chain PASSED
tests/test_options.py::TestOptionsAnalysis::test_calculate_implied_volatility PASSED
tests/test_options.py::TestOptionsAnalysis::test_greeks_model PASSED
tests/test_options.py::TestOptionsAnalysis::test_expired_contract_error_attributes PASSED
tests/test_options.py::TestOptionsAnalysis::test_calculate_var PASSED
tests/test_options.py::TestOptionsAnalysis::test_edge_cases PASSED
tests/test_options.py::TestOptionsAnalysis::test_get_atm_strike PASSED
tests/test_options.py::TestOptionsAnalysis::test_calculate_greeks PASSED
tests/test_options.py::TestOptionsAnalysis::test_option_contract_model PASSED
tests/test_options.py::TestOptionsAnalysis::test_calculate_historical_var PASSED
tests/test_options.py::TestOptionsAnalysis::test_calculate_volatility_analysis PASSED

============================= 14 passed in 2.14s ==============================
```

## Behavior Change

| Scenario | Before | After |
|----------|--------|-------|
| t = 0.0 | Returns clamped Greeks (t=0.0001) | Raises `ExpiredContractError` |
| t < 0 | Returns clamped Greeks (t=0.0001) | Raises `ExpiredContractError` |
| t = 0.0, allow_expired=True | N/A | Returns Greeks |
| t = 0.00005 | Returns Greeks (clamped to 0.0001) | Returns Greeks (clamped to 0.0001) |

## Remaining Clamping

The only remaining clamping is for very small positive values (`t < 0.0001`) to prevent numerical instability in Black-Scholes calculations. This is intentional and necessary for mathematical stability.

## Files Modified

1. `src/loats/options.py` - Added exception class and replaced 5 silent clamping instances
2. `tests/test_options.py` - Updated tests to verify new error behavior

## Status: ✅ COMPLETE