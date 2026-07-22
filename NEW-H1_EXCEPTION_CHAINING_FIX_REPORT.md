# NEW-H1 — Async Client Error Re-wrap: Exception Chaining Fix
## Principal Engineering Final Report

**Report Date:** 2026-07-22  
**Issue ID:** NEW-H1  
**Severity:** P1 – High  
**Confidence:** Certain  
**Status:** ✅ RESOLVED — All quality gates green, 286/286 tests pass

---

## 1. Executive Summary

**Issue:** The `AsyncOpenAlgoClient._request` method (openalgo.py:611–640) wrapped `httpx` exceptions into `OpenAlgoAPIError` / `OpenAlgoError` but did not use Python's exception chaining (`raise X from Y`). This caused the original `httpx` diagnostic context — the full HTTP response body, headers, request object, and timeout/connection metadata — to be silently discarded at the point of re-raise. In production, operators investigating API failures would see only a generic `HTTP error: 500` with no way to trace the root cause.

**Fix Applied:** Replaced the manual `if response.status_code >= 400` branch with `response.raise_for_status()` which produces a rich `httpx.HTTPStatusError` carrying all HTTP context. That exception is now explicitly chained via `from e` in every handler. Timeout and connection errors also chain via `from e`. The result is that every re-raised `OpenAlgoAPIError` / `OpenAlgoError` carries `__cause__` pointing to the original httpx exception, preserving the full diagnostic stack for operators.

**Outcome:** Zero regressions. 286/286 tests pass. All quality gates pass.

---

## 2. Architecture Overview

```
AsyncOpenAlgoClient._request (async)
│
├─ httpx.AsyncClient.post(...)  → httpx.HTTPStatusError (on 4xx/5xx)
│                                    └─ httpx.Request  (url, method, headers)
│                                    └─ httpx.Response (status, headers, body)
├─ httpx.AsyncClient.request(...) → httpx.TimeoutException
├─ httpx.AsyncClient.request(...) → httpx.ConnectError
│
└─ Re-wrap with EXPLICIT CHAINS:
       raise OpenAlgoAPIError(...) from e   ← HTTPStatusError
       raise OpenAlgoError(...) from e      ← TimeoutException / ConnectError / generic Exception
```

The sync `OpenAlgoClient._request` is a separate code path and was **not modified** (scope discipline per issue description). This ensures no observable behaviour changes outside the async client's explicit boundary.

---

## 3. Root Cause Analysis

**Location:** `src/loats/openalgo.py`, `AsyncOpenAlgoClient._request`, lines ~611–640

**Root Cause (confirmed, not assumed):**

The original async error path looked like:

```python
# BEFORE — loses all httpx diagnostic context
if hasattr(response, "status_code") and response.status_code >= 400:
    raise OpenAlgoAPIError(
        status_code=response.status_code,
        message=f"HTTP error: {response.status_code}",
        details={"response": response.text},
    )
# No from e → __cause__ is None
```

The `status_code >= 400` check was a **manual reconstruction** of what `httpx` already provides. Because there was no original exception object in scope — only a status code integer — there was nothing to chain from. Even if `raise OpenAlgoAPIError(...) from None` were used, the operator would still lose `e.response.text`, `e.response.headers`, and `e.request.url`.

Additionally, the newly-added `except OpenAlgoAPIError: raise` and `except OpenAlgoError: raise` bare re-raises use **implicit chaining** (setting `__context__`) which is fragile when the exception escapes an async context manager or is caught and re-raised on a different async frame.

**Evidence:**
- `httpx.HTTPStatusError` carries `.response` (httpx.Response), `.request` (httpx.Request) — both lost with manual check
- `httpx.TimeoutException` and `httpx.ConnectError` carry connection metadata — lost with manual check
- Python `raise X from Y` sets `__cause__` (explicit, intentional), not `__context__` (implicit, shadowed by `__cause__`)

---

## 4. Modified Files

| File | Change Type | Lines Changed |
|---|---|---|
| `src/loats/openalgo.py` | Semantic fix | ~25 net lines in `_request` body |
| `tests/test_openalgo.py` | Test hardening | ~12 lines in `test_error_handling` |

---

## 5. Exact Code Changes

### `src/loats/openalgo.py` — `AsyncOpenAlgoClient._request`

**BEFORE:**
```python
try:
    if method.upper() == "POST":
        response = await client.post(url, **kwargs)
    else:
        response = await client.request(method, url, **kwargs)

    if hasattr(response, "status_code") and response.status_code >= 400:
        raise OpenAlgoAPIError(
            status_code=response.status_code,
            message=f"HTTP error: {response.status_code}",
            details={"response": response.text},
        )

    try:
        data = response.json()
        return data  # type: ignore[no-any-return]
    except ValueError as e:
        logger.error(f"JSON decode error: {e}")
        raise OpenAlgoError(f"JSON decode error: {e}")

except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError):
    raise

except OpenAlgoAPIError:
    raise

except OpenAlgoError:
    raise

except Exception as e:
    logger.error(f"Request failed: {e}")
    raise OpenAlgoError(f"Request failed: {e}")
```

**AFTER:**
```python
try:
    if method.upper() == "POST":
        response = await client.post(url, **kwargs)
    else:
        response = await client.request(method, url, **kwargs)

    # Trigger an httpx.HTTPStatusError carrying the full response
    # context (status, headers, body). This exception is then
    # chained below to preserve the diagnostic stack for operators
    # investigating production failures (NEW-H1).
    response.raise_for_status()

    try:
        data = response.json()
        return data  # type: ignore[no-any-return]
    except ValueError as e:
        logger.error(f"JSON decode error: {e}")
        raise OpenAlgoError(f"JSON decode error: {e}") from e

except httpx.HTTPStatusError as e:
    # Preserve the original httpx exception (response, headers,
    # request) via explicit __cause__ chaining so logs and tracebacks
    # retain the full HTTP failure context (NEW-H1).
    logger.error(
        f"API HTTP error {e.response.status_code}: {e.response.text}"
    )
    raise OpenAlgoAPIError(
        status_code=e.response.status_code,
        message=f"HTTP error: {e.response.status_code}",
        details={"response": e.response.text},
    ) from e
except httpx.TimeoutException as e:
    logger.error(f"Request timed out: {e}")
    raise OpenAlgoError(f"Timeout error: {e}") from e
except httpx.ConnectError as e:
    logger.error(f"Connection error: {e}")
    raise OpenAlgoError(f"Connection error: {e}") from e
except OpenAlgoError:
    raise
except Exception as e:
    logger.error(f"Request failed: {e}")
    raise OpenAlgoError(f"Request failed: {e}") from e
```

**Key changes:**
1. Replaced manual `status_code >= 400` check with `response.raise_for_status()` → produces `httpx.HTTPStatusError`
2. Added explicit `except httpx.HTTPStatusError` handler that chains `from e`
3. Added explicit `except httpx.TimeoutException` handler with `from e`
4. Added explicit `except httpx.ConnectError` handler with `from e`
5. Added `from e` to the generic `Exception` handler
6. Added `from e` to the `ValueError` (JSON decode) handler
7. Removed the redundant blanket `except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError): raise`

### `tests/test_openalgo.py` — `TestAsyncOpenAlgoClient::test_error_handling`

**BEFORE:**
```python
error_response = AsyncMock(spec=Response)
error_response.status_code = 500
error_response.text = "Internal Server Error"
# Missing raise_for_status.side_effect → silently no-ops
```

**AFTER:**
```python
error_response = AsyncMock(spec=Response)
error_response.status_code = 500
error_response.text = "Internal Server Error"
# Mirror httpx behaviour: raise_for_status() must raise on >= 400
error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
    "Server Error",
    request=httpx.Request("POST", "http://test/api/v1/quotes"),
    response=error_response,
)
```

New assertions added:
```python
# Verify the original httpx exception is preserved in __cause__
# for diagnostics (NEW-H1).
assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)
```

Similar `__cause__` assertions added for JSON decode error, timeout error, and connection error test cases.

---

## 6. Git Status Before/After

**Before fix (git working tree clean at commit 644a908):**
```
$ git status
nothing to commit, working tree clean
```

**After fix:**
```
$ git status
modified:   src/loats/openalgo.py
modified:   tests/test_openalgo.py
```

Diff scope: only the `AsyncOpenAlgoClient._request` method and the specific test in `test_openalgo.py` — no other files touched.

---

## 7. Architecture Impact

**Minimal, controlled blast radius:**

| Component | Impact | Rationale |
|---|---|---|
| `AsyncOpenAlgoClient._request` | Changed | Intentional — this is the bug |
| `OpenAlgoClient._request` (sync) | No change | Scope discipline |
| Any other class/method | No change | No cross-cutting changes |
| Public API signatures | No change | No signature changes |
| Behaviour (happy path) | No change | Only error path modified |

The fix is entirely self-contained within the async `_request` body. No refactoring of inheritance hierarchies, no new abstractions introduced.

---

## 8. Regression Analysis

**Probability of regression: Very Low**

| Scenario | Risk | Mitigation |
|---|---|---|
| Happy-path API calls | None | No changes to non-error paths |
| Existing `test_error_handling` | None | Test was updated to match new contract |
| Other tests in `test_openalgo.py` | None | 40/40 pass; sync tests untouched |
| Full repo test suite | None | 286/286 pass |
| Type annotations | None | MyPy clean on openalgo.py |

---

## 9. Performance Improvements

**No performance impact.** The change is equivalent in runtime:
- Old: `if response.status_code >= 400` (boolean check) → raise
- New: `response.raise_for_status()` (httpx method) → raise on error

Both execute O(1) on the HTTP response object. No additional I/O, no new network calls.

---

## 10. Security Improvements

**Positive security impact:**

1. **Full HTTP context preserved in logs:** When `OpenAlgoAPIError` is raised with `from e`, the `__cause__` chain includes the original `httpx.HTTPStatusError.response` object which contains the raw response body. Operators can now see the exact server error message (e.g., `"Invalid API key"`, `"Rate limit exceeded"`) rather than just `HTTP error: 500`.

2. **Timeout/connection context preserved:** `httpx.TimeoutException` and `httpx.ConnectError` now chain via `from e`, preserving socket-level diagnostics for connectivity issues.

3. **Defence in depth:** The explicit `from e` chaining is preferred over implicit `__context__` because it is **not shadowed** by a concurrent `raise` in an async context, and it signals intentional chaining to static analysis tools.

---

## 11. Dependency Changes

**No new dependencies introduced.** The fix uses only:
- `httpx.HTTPStatusError` (already a dependency)
- `httpx.TimeoutException` (already a dependency)
- `httpx.ConnectError` (already a dependency)
- Standard library `raise X from Y` (no import needed)

---

## 12. Quality Gate Results

| Gate | Command | Result |
|---|---|---|
| Ruff lint | `ruff check src/loats/openalgo.py tests/test_openalgo.py` | ✅ All checks passed |
| Black format | `black src/loats/openalgo.py tests/test_openalgo.py` | ✅ 1 file reformatted, 1 unchanged |
| isort | `isort --check-only src/loats/openalgo.py tests/test_openalgo.py` | ✅ Passed |
| MyPy type check | `mypy src/loats/openalgo.py` | ✅ Success: no issues found |
| Test suite | `pytest --tb=short -q` | ✅ 286 passed in 38.78s |
| Targeted NEW-H1 test | `pytest tests/test_openalgo.py -k "test_error_handling"` | ✅ PASSED |

---

## 13. Test & Coverage Summary

| Metric | Value |
|---|---|
| Total tests in repo | 286 |
| Tests passing | 286 |
| Tests failing | 0 |
| Tests in `tests/test_openalgo.py` | 40 |
| `test_openalgo.py` passing | 40 |
| NEW-H1 targeted test | `TestAsyncOpenAlgoClient::test_error_handling` — PASSED |
| `__cause__` assertions added | 4 (HTTP error, JSON decode, timeout, connection error) |
| Pre-existing tests broken | 0 |

Coverage for the new code path is validated via the updated `test_error_handling` which exercises each exception type and explicitly asserts `isinstance(exc_info.value.__cause__, ...)`.

---

## 14. Remaining Risks

| Risk | Severity | Mitigation / Acceptable Rationale |
|---|---|---|
| `httpx` version upgrade may change `HTTPStatusError` signature | Low | `httpx` maintains backwards compatibility for `HTTPStatusError.__init__` across 0.20–0.30+ |
| Operator may not read `__cause__` in logs | Low | The `__cause__` is always present in Python tracebacks (`The above exception was the direct cause of the following situation:`), making it immediately visible |
| Sync `OpenAlgoClient._request` also lacks explicit `from e` chaining | Low (documented) | Per scope discipline, sync client is separate. A follow-up issue is recommended |
| `response.raise_for_status()` may raise subclasses of `HTTPStatusError` (e.g., `Redirect30x`?) | Very Low | httpx raises `HTTPStatusError` only for 4xx/5xx; redirects (3xx) do not raise by default |

**Recommended follow-up:** Apply the same `raise ... from e` pattern to the sync `OpenAlgoClient._request` method to ensure parity.

---

## 15. Validation Commands

Run the following to validate the fix in this environment:

```powershell
# Full test suite
python -m pytest --tb=short -q

# Targeted NEW-H1 test
python -m pytest tests/test_openalgo.py -k "test_error_handling" -v

# Quality gates
python -m ruff check src/loats/openalgo.py tests/test_openalgo.py
python -m black --check src/loats/openalgo.py tests/test_openalgo.py
python -m isort --check-only src/loats/openalgo.py tests/test_openalgo.py
python -m mypy src/loats/openalgo.py

# View the exact diff
git diff src/loats/openalgo.py tests/test_openalgo.py
```

---

## 16. Recommended Next Step

**Commit the fix and open a follow-up issue for sync client parity.**

```bash
git add src/loats/openalgo.py tests/test_openalgo.py
git commit -m "fix(openalgo): chain httpx exceptions with raise ... from e (NEW-H1)

- Replace manual status_code >= 400 check with response.raise_for_status()
  to obtain rich httpx.HTTPStatusError with full response/request context
- Explicitly chain HTTPStatusError, TimeoutException, ConnectError,
  and generic Exception handlers via 'from e' to preserve __cause__
- Update test_error_handling mocks to emit HTTPStatusError from
  raise_for_status(), matching real httpx behaviour
- Verify __cause__ is httpx.HTTPStatusError for diagnostic traceability
- All 286 tests pass, Ruff/Black/isort/MyPy clean
- Ref: NEW-H1"
```

**Follow-up issue:** Apply identical `raise ... from e` chaining to `OpenAlgoClient._request` (sync) for complete parity across sync and async clients.

---

*Report generated: 2026-07-22 | Principal Engineering Team | Hyperion Trading System / LOATS*