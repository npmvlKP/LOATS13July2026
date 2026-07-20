# LOATS13July2026 Project Health Recovery Task List

## 🚀 Phase 1: Git Repository Cleanup
- [ ] Update .gitignore to properly exclude virtual environment files
- [ ] Remove virtual environment files from git staging area
- [ ] Clean up git repository to have 0 pending changes
- [ ] Verify git status shows clean working directory

## 🔧 Phase 2: Virtual Environment Recovery
- [ ] Remove corrupted virtual environment
- [ ] Create new clean virtual environment
- [ ] Install all dependencies from requirements-core.txt
- [ ] Verify virtual environment activation and functionality
- [ ] Fix pyvenv.cfg file in root directory

## 🐛 Phase 3: Critical Import Fixes
- [ ] Identify which critical imports are failing
- [ ] Fix import paths and dependencies
- [ ] Verify all critical imports work correctly

## ✅ Phase 4: Code Quality Fixes
- [ ] Fix line length violation in src/loats/models.py
- [ ] Run ruff linter to identify and fix other code quality issues
- [ ] Verify all code quality checks pass

## 🔒 Phase 5: Type Safety & Security
- [ ] Verify mypy is properly installed and available
- [ ] Run mypy type checking and fix any issues
- [ ] Verify bandit is properly installed and available
- [ ] Run bandit security scan and fix any issues

## 🧪 Phase 6: Testing & Verification
- [ ] Run all Python tests to ensure they pass
- [ ] Verify quick_health_check.py passes all checks
- [ ] Verify verify_project_health.py passes all checks
- [ ] Run comprehensive test suite

## 📊 Phase 7: Final Verification
- [ ] Verify git repository is clean with 0 pending changes
- [ ] Verify all health checks pass
- [ ] Verify project is deploy-ready and stable
- [ ] Prepare final report with root cause analysis and resolution

## 🛡️ Phase 8: F-CONC-3 Rate Guard Bug Fix
- [x] Analyze `src/loats/utils/nim_rate_guard.py` - understand current implementation
- [x] Identify all usages of `NimRateGuard` in the codebase
- [x] Implement module-level singleton fix (move `_guard` from local variable to module-level)
- [x] Run quality gates (Ruff, MyPy, Flake8) - all passed
- [x] Run tests to verify no regressions - 237 tests passed
- [ ] Verify rate limiter behavior (manual verification completed - singleton ensures state persistence)

### Bug Fix Details (F-CONC-3)
**Root Cause:** `NimRateGuard` was instantiated inside `nim_call_with_backoff()` at line 96, creating a fresh instance with empty state on every call.

**Impact:** Rate limiter was ineffective - sliding window and gap checks never accumulated state, allowing NVIDIA NIM API to be hammered with concurrent requests.

**Resolution:** Moved `_guard = NimRateGuard()` to module-level (end of file), ensuring a single shared instance tracks call timestamps and enforces ≤20 req/min with ≥3s gap.

**Modified Files:**
- `src/loats/utils/nim_rate_guard.py` - singleton pattern implementation
