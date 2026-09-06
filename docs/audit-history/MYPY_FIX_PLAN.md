# MyPy Fix Plan - 88 errors in 9 files

## Priority 1: Simple type annotation fixes (rate_limiter.py - 2 errors)
- [ ] Line 134: Add type annotation for `clock` parameter in `AsyncRateLimiter.__init__`
- [ ] Line 504: Add type annotation for `clock` parameter in `create_test_rate_limiter`

## Priority 2: database_async_additions.py (32 errors)
- [ ] Lines 533-605: Fix the `_async_` method naming - they should be `async_` not `_async_`
- [ ] Lines 617-633: Fix class-level method assignments using wrong names

## Priority 3: trailing_stop.py (4 errors)
- [ ] Line 462: Add missing `filled_quantity` argument to Order constructor
- [ ] Lines 472-475: Fix type mismatches for Order fields (variety, product_type, status)

## Priority 4: sizing.py (2 errors)
- [ ] Line 413: Fix return type and SizingMethod.MARGIN_AWARE attribute issue

## Priority 5: options.py (16 errors)
- [ ] Lines 714, 716: Fix numpy floating type assignments
- [ ] Line 720: Fix None + float and float * None operations
- [ ] Lines 791, 794, 797, 822: Trade.current_price attribute missing
- [ ] Lines 807, 838, 860, 883, 934: datetime.UTC and datetime.datetime issues

## Priority 6: rules.py (1 error)
- [ ] Line 322: Add type annotation for source_trades

## Priority 7: performance_analyzer.py (10 errors)
- [ ] Add type annotations to all functions missing them

## Priority 8: trade_decision.py (4 errors)
- [ ] Line 45: Add type annotation for decision_queue
- [ ] Line 145: Add missing entry_time to Trade constructor
- [ ] Lines 326-327: Fix _processor_task type

## Priority 9: orchestrator.py (17 errors)
- [ ] Line 115: Fix unreachable statement
- [ ] Line 121: Fix Task[None] vs None assignment, add await
- [ ] Line 122: Fix None.add_done_callback
- [ ] Line 143: Fix float vs int assignment
- [ ] Lines 216, 217, 284, 314, 350, 401, 540: Fix Settings | None union attribute access
- [ ] Line 596: Fix Database.get_positions vs get_position
- [ ] Line 730: Fix unreachable statement
- [ ] Line 825: Add type arguments for Task