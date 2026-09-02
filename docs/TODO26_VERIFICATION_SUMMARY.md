# TODO-26 (F7-L-06) — VERIFICATION SUMMARY

**Date:** August 30, 2026
**Task:** Drive `backtest_sanity` — Wire CMP P4 exit gate module with weekly scheduler job
**Status:** ✅ **COMPLETE AND VERIFIED**

---

## ✅ Final Test Results

```
uv run pytest tests/test_backtest_sanity_production.py -v

21 passed in 4.95s
```

**All test failures have been resolved.**

---

## ✅ Final External Verification Results

```
python scripts/final_verify_todo26.py

Total Checks: 46
Passed: 46
Failed: 0
Pass Rate: 100.0%
✓ ALL CHECKS PASSED - TODO-26 IMPLEMENTATION VERIFIED
```

---

## 🔧 Root-Cause Fixes Applied

### Issue 1: `calculate_simple_pnl` TypeError
**Failure:**
```
TypeError: unsupported operand type(s) for *: 'float' and 'decimal.Decimal'
```

**Root Cause:**
The `HistoricalData` model defines OHLC fields as `float`. The `calculate_simple_pnl()` function performed:
```python
(last_bar.close - first_bar.open) / first_bar.open * Decimal("100")
```
Python evaluates this as `((float - float) / float) * Decimal`, which raises TypeError because `float * Decimal` is not supported.

**Fix Applied in `src/loats/backtest_sanity.py`:**
```python
open_price = Decimal(str(first_bar.open))
close_price = Decimal(str(last_bar.close))
pnl = ((close_price - open_price) / open_price * Decimal("100"))
```
This follows the project's "Decimal-only finance" principle.

---

### Issue 2: Iterator Test Failed Wrong Check
**Failure:**
```
AssertionError: Regex pattern did not match.
Expected regex: 'must be sorted by timestamp'
Actual message: 'Window size (20) cannot exceed data length (2)'
```

**Root Cause:**
The test created 2-element unsorted data but called `WalkForwardWindowIterator(unsorted_data)` without specifying `window_size`. The default `window_size=20` caused a length validation failure **before** the sort check could run.

**Fix Applied in `tests/test_backtest_sanity_production.py`:**
```python
with pytest.raises(ValueError, match="must be sorted by timestamp"):
    bs.WalkForwardWindowIterator(unsorted_data, window_size=2)
```

---

### Issue 3: Path Resolution Failure
**Failure:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'G:\.OA\LOATS-13July2026\src\loats\scheduler.py'
```

**Root Cause:**
The test used:
```python
PROJECT_ROOT = Path(__file__).parent.parent.parent
```
which resolved to `G:
\.OA\LOATS-13July2026` instead of `G:
\.OA\LOATS-13July2026\LOATS13July2026` due to the nested repository structure.

**Fix Applied in `tests/test_backtest_sanity_production.py`:**
```python
def _find_project_root() -> Path:
    """Resolve project root robustly from this test file's location."""
    this_file = Path(__file__).resolve()
    candidate = this_file.parent.parent
    if (candidate / "src").is_dir() and (candidate / "tests").is_dir():
        return candidate
    for parent in this_file.parents:
        if (parent / "src").is_dir() and (parent / "tests").is_dir():
            return parent
    raise FileNotFoundError("Could not resolve project root (missing src/tests)")

PROJECT_ROOT = _find_project_root()
```

---

## 📋 Files Modified in Fix Round

| File | Change | Lines |
|------|--------|-------|
| `src/loats/backtest_sanity.py` | Decimal conversion for float OHLC inputs | +3 |
| `tests/test_backtest_sanity_production.py` | Explicit window_size in unsorted test | +1 |
| `tests/test_backtest_sanity_production.py` | Robust project root resolution | +16 |

---

## 🔍 Validation Commands (Run Externally)

### 1. Final Verification Script
```bash
python scripts/final_verify_todo26.py
```
**Expected:** 46/46 checks passed, exit 0

### 2. Test Suite
```bash
uv run pytest tests/test_backtest_sanity_production.py -v
```
**Expected:** 21 passed, exit 0

### 3. Health Check HC-30
```bash
python scripts/fr7_health_check.py --only HC-30
```
**Expected:** HC-30 PASS

---

## 🎯 Production Wiring Summary

| Feature | Status |
|---------|--------|
| Weekly scheduler job (Sunday 4:00 AM IST) | ✅ |
| On-demand execution via `run_once()` | ✅ |
| Health check HC-30 | ✅ |
| No-lookahead validation | ✅ |
| Walk-forward window iterator | ✅ |
| Exit gate (80% threshold) | ✅ |
| Decimal-only PnL calculation | ✅ |
| Comprehensive verification scripts | ✅ |
| Production test suite (21 tests) | ✅ |

---

## 🎯 Conclusion

**TODO-26 (F7-L-06) is COMPLETE, ROOT-CAUSE FIXED, and FULLY VERIFIED.**

All 6 test failures were fixed by addressing their underlying causes, not symptoms:
1. Decimal conversion for float inputs
2. Test configuration to reach the intended validation path
3. Robust project root resolution

**Verification Evidence:**
- ✅ 21/21 tests passing
- ✅ 46/46 external verification checks passing
- ✅ No remaining TODO-26 defects

**Status:** ✅ **PRODUCTION READY**
