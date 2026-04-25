---
phase: 14-trade-journal-mutation-endpoints
plan: 01
subsystem: testing
tags: [pytest, htmx, hex-boundary, fixtures, scaffolding, schema-migration]

# Dependency graph
requires:
  - phase: 13-auth-read-endpoints
    provides: 'tests/conftest.py autouse WEB_AUTH_SECRET fixture; TestWebHexBoundary FORBIDDEN_FOR_WEB pattern with dashboard promotion regression'
provides:
  - 'tests/test_web_trades.py — 13 named skeleton classes covering TRADE-01..06 + D-01..D-13 (Plan 14-04 fills)'
  - 'tests/test_state_manager.py — TestFcntlLock + TestSchemaMigrationV2ToV3 skeletons (Plan 14-02 fills)'
  - 'tests/test_sizing_engine.py — TestManualStopOverride skeleton (Plan 14-03 fills)'
  - 'tests/test_dashboard.py — TestRenderDashboardHTMXVendorPin + TestRenderPositionsTableHTMXForm + TestRenderManualStopBadge skeletons (Plan 14-05 fills)'
  - 'tests/conftest.py — htmx_headers + client_with_state_v3 fixtures (used by all subsequent Phase 14 plans)'
  - 'tests/fixtures/state_v2_no_manual_stop.json — v2-schema state with two open Positions and NO manual_stop key (binding contract for Plan 14-02 v2->v3 migration round-trip test)'
  - 'TestWebHexBoundary.FORBIDDEN_FOR_WEB promotion: sizing_engine + system_params dropped (Phase 14 D-02); two new regression tests lock the absence'
affects: [14-02, 14-03, 14-04, 14-05]

# Tech tracking
tech-stack:
  added: []  # Wave 0 ships zero new dependencies; pytest, fastapi.testclient already present from Phase 11/13
  patterns:
    - 'Skeleton-class-with-pytest.skip pattern: pytest collection passes for incomplete plans, every skeleton method skips with the implementing-plan reference'
    - 'Phase 14 v3-schema state fixture (client_with_state_v3) returns (TestClient, set_state, captured_saves) tuple for atomic-single-save assertions'
    - 'Hex-boundary frozenset promotion mirror pattern (Phase 13 D-07 -> Phase 14 D-02): drop module from FORBIDDEN_FOR_WEB + append a regression test asserting the absence by name'

key-files:
  created:
    - 'tests/test_web_trades.py — 13 skeleton classes + path constant for TestSoleWriterInvariant AST walk'
    - 'tests/fixtures/state_v2_no_manual_stop.json — v2 fixture for migration round-trip'
  modified:
    - 'tests/test_web_healthz.py — TestWebHexBoundary.FORBIDDEN_FOR_WEB drops sizing_engine + system_params; +2 regression tests'
    - 'tests/conftest.py — append htmx_headers + client_with_state_v3 fixtures'
    - 'tests/test_state_manager.py — append TestFcntlLock + TestSchemaMigrationV2ToV3 skeletons'
    - 'tests/test_sizing_engine.py — append TestManualStopOverride skeleton'
    - 'tests/test_dashboard.py — append TestRenderDashboardHTMXVendorPin + TestRenderPositionsTableHTMXForm + TestRenderManualStopBadge skeletons'

key-decisions:
  - 'Promote both sizing_engine AND system_params out of FORBIDDEN_FOR_WEB (Option A from 14-PATTERNS.md). Single-source-of-truth preserved (no duplicate MAX_PYRAMID_LEVEL constant in web/routes/trades.py)'
  - 'Do NOT extend test_web_adapter_imports_are_local_not_module_top.forbidden_module_top — sizing_engine/system_params LOCAL-import discipline in trades.py is a Plan 04 convention, not a Phase 14 hex-rule change'
  - 'v2 fixture has both SPI200 LONG (peak_price set, trough_price=null) AND AUDUSD SHORT (trough_price set, peak_price=null) — exercises BOTH directions of Phase 2 D-08 invariant'

patterns-established:
  - 'Wave 0 contract: 14-VALIDATION.md class enumeration -> grep-able literal class names in skeleton file -> Plan 14-04 has a deterministic fill-in map'
  - 'client_with_state_v3 closure pattern: (TestClient, set_state, captured_saves) tuple yields both injection and observation in one fixture'

requirements-completed: []  # Wave 0 is scaffolding only; TRADE-01..06 listed in plan frontmatter are completed by Plans 02..05 collectively

# Metrics
duration: 7min
completed: 2026-04-25
---

# Phase 14 Plan 01: Wave 0 Test Infrastructure Scaffolding Summary

**Skeleton-only Wave 0: 13 named test classes for the TRADE-01..06 endpoint surface, two new conftest fixtures (htmx_headers + v3-schema TestClient with save-capture closure), one v2-schema migration fixture, and a hex-boundary frozenset promotion (sizing_engine + system_params) with two regression tests — all green under `pytest -x`, zero production-code changes.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-04-25T08:33:42Z
- **Completed:** 2026-04-25T08:40:43Z
- **Tasks:** 2
- **Files modified:** 5
- **Files created:** 2

## Accomplishments

- TestWebHexBoundary.FORBIDDEN_FOR_WEB promotion: sizing_engine and system_params dropped per Phase 14 D-02, mirroring the Phase 13 D-07 dashboard precedent. Two new regression tests lock the absence so a future plan that re-adds either fires red immediately.
- 13 named skeleton classes in tests/test_web_trades.py covering the entire TRADE-01..06 surface: open/pyramid-up/advanced-fields/close/PnL-math/modify/absent-vs-null/error-responses/HTMX/HTMX-support/save-state-invariant/sole-writer-invariant/end-to-end. Plan 14-04 has a deterministic fill-in map.
- v2-schema fixture (tests/fixtures/state_v2_no_manual_stop.json) with two open Positions (SPI200 LONG with peak, AUDUSD SHORT with trough) and NO manual_stop key — the binding contract for the Plan 14-02 v2->v3 migration round-trip test.
- Two conftest fixtures: htmx_headers (auth + HX-Request: true) and client_with_state_v3 returning a (TestClient, set_state, captured_saves) tuple for the atomic-single-save assertions Plan 14-04 requires.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 hex-boundary update + v2 fixture + conftest extensions** — `4107924` (test)
2. **Task 2: Wave 0 skeleton test files for Plans 02-05** — `36cd3da` (test)

## FORBIDDEN_FOR_WEB before/after (proves the promotion)

**Before (Phase 13):**
```python
FORBIDDEN_FOR_WEB = frozenset({
  'signal_engine', 'sizing_engine', 'system_params',
  'data_fetcher', 'notifier', 'main',
})
```

**After (Phase 14 Plan 14-01):**
```python
FORBIDDEN_FOR_WEB = frozenset({
  'signal_engine',
  'data_fetcher', 'notifier', 'main',
})
```

Two new regression tests appended INSIDE TestWebHexBoundary:
- `test_sizing_engine_is_not_forbidden_for_web_phase_14_D02`
- `test_system_params_is_not_forbidden_for_web_phase_14`

## 13 skeleton class names in tests/test_web_trades.py (Wave 0 contract)

1. TestOpenTradeEndpoint — POST /trades/open happy path + validation
2. TestOpenPyramidUp — D-01/D-02 same/opposite-direction routing
3. TestOpenAdvancedFields — D-03 peak/trough/pyramid_level coherence
4. TestCloseTradeEndpoint — POST /trades/close + D-05/D-06/D-07
5. TestCloseTradePnLMath — LONG/SHORT inline raw price-delta formula
6. TestModifyTradeEndpoint — POST /trades/modify all D-09..D-12 cases
7. TestModifyAbsentVsNull — Pydantic v2 model_fields_set semantics (D-12)
8. TestErrorResponses — 422->400 remap + field-level error JSON shape
9. TestHTMXResponses — UI-SPEC §Decision 3 response shapes + OOB banner + HX-Trigger
10. TestHTMXSupportEndpoints — GET /trades/close-form, /trades/modify-form, /trades/cancel-row
11. TestSaveStateInvariant — TRADE-06 atomic-single-save closure assertion
12. TestSoleWriterInvariant — RESEARCH §Pattern 10 AST walk (web/routes/trades.py is sole writer of state['warnings'])
13. TestEndToEnd — full request lifecycle

## pytest output excerpt (proves the skip discipline)

`pytest tests/test_web_trades.py tests/test_state_manager.py tests/test_sizing_engine.py tests/test_dashboard.py tests/test_web_healthz.py -x -q`:

```
291 passed, 19 skipped in 0.69s
```

19 skipped breakdown:
- 13 in test_web_trades.py (one per skeleton class) — Plan 14-04 fills
- 2 in test_state_manager.py (TestFcntlLock, TestSchemaMigrationV2ToV3) — Plan 14-02 fills
- 1 in test_sizing_engine.py (TestManualStopOverride) — Plan 14-03 fills
- 3 in test_dashboard.py (HTMXVendorPin, PositionsTableHTMXForm, ManualStopBadge) — Plan 14-05 fills

`pytest --collect-only tests/test_web_trades.py | grep -c test_placeholder_wave_0` returns 13.

Full-suite (excluding test_main.py): 877 passed, 19 skipped (was 875 + 0 baseline; +2 new TestWebHexBoundary regression tests = 877; +19 skip placeholders).

test_main.py: 16 pre-existing weekend-skip failures unchanged (deferred-items.md baseline).

## Files Created/Modified

**Created:**
- `tests/test_web_trades.py` — 13 skeleton classes for Phase 14 endpoint contract tests
- `tests/fixtures/state_v2_no_manual_stop.json` — v2-schema fixture for migration round-trip

**Modified:**
- `tests/test_web_healthz.py` — TestWebHexBoundary.FORBIDDEN_FOR_WEB promotion + 2 regression tests
- `tests/conftest.py` — appended htmx_headers + client_with_state_v3 fixtures
- `tests/test_state_manager.py` — appended TestFcntlLock + TestSchemaMigrationV2ToV3 skeletons
- `tests/test_sizing_engine.py` — appended TestManualStopOverride skeleton
- `tests/test_dashboard.py` — appended TestRenderDashboardHTMXVendorPin + TestRenderPositionsTableHTMXForm + TestRenderManualStopBadge skeletons

## Decisions Made

- **Option A from 14-PATTERNS.md (promote both sizing_engine + system_params).** Inlining MAX_PYRAMID_LEVEL=2 as a duplicate constant in web/routes/trades.py (Option B) was rejected — single-source-of-truth preserved. Pydantic model_validator bodies in trades.py will import MAX_PYRAMID_LEVEL locally per RESEARCH §Pattern 1 line 343, and the AST walker walks function bodies, so a forbidden module cannot be locally-imported anywhere in web/.
- **test_web_adapter_imports_are_local_not_module_top NOT extended.** Per the plan's CRITICAL note (lines 202-203), Phase 14 hex-boundary discipline is: (a) modules in FORBIDDEN_FOR_WEB cannot be imported at all from web/ (full prohibition); (b) modules in forbidden_module_top can be imported LOCAL-only inside handlers. Plan 04 will use LOCAL imports inside handlers for state_manager, sizing_engine, and system_params constants by convention but the AST guard only enforces (a) and (b)-state_manager-and-dashboard. Adding system_params to (b) would force every constant lookup to be local — that's a Plan 04 convention, not a Phase 14 hex-rule change.
- **v2 fixture covers BOTH directions of the Phase 2 D-08 peak/trough invariant.** SPI200 LONG has peak_price=7850 + trough_price=null; AUDUSD SHORT has trough_price=0.6420 + peak_price=null. This exercises both branches of the migration backfill.

## Deviations from Plan

None — plan executed exactly as written. No Rule 1/2/3 fixes were necessary.

The plan's documented "deviations" (sub-edit A's promotion of both sizing_engine AND system_params, the choice between Option A and Option B) were resolved at planning time via the explicit Option A selection in the plan body itself; this executor merely implemented the planner's choice.

One minor stylistic touch: I introduced a `_pytest` import alias in conftest.py while writing the fixtures and then immediately removed it (the alias was unnecessary because the module-top `import pytest` is in scope inside fixture bodies). The first edit produced a working file; the second edit cleaned up the cosmetic redundancy. No semantic change; not tracked as a deviation.

---

**Total deviations:** 0 auto-fixed
**Impact on plan:** Plan executed exactly as written. Zero production-code changes (test infrastructure only); zero new failures vs deferred-items.md baseline.

## Issues Encountered

None.

## User Setup Required

None — Wave 0 is test scaffolding only. No environment variables, no external services, no manual configuration.

## Self-Check

**Files exist:**
- FOUND: tests/test_web_trades.py
- FOUND: tests/fixtures/state_v2_no_manual_stop.json
- FOUND: tests/conftest.py (modified — htmx_headers + client_with_state_v3 present)
- FOUND: tests/test_web_healthz.py (modified — FORBIDDEN_FOR_WEB updated)
- FOUND: tests/test_state_manager.py (modified — TestFcntlLock + TestSchemaMigrationV2ToV3 appended)
- FOUND: tests/test_sizing_engine.py (modified — TestManualStopOverride appended)
- FOUND: tests/test_dashboard.py (modified — three HTMX/badge skeletons appended)

**Commits exist:**
- FOUND: 4107924 (Task 1)
- FOUND: 36cd3da (Task 2)

## Self-Check: PASSED

## Next Phase Readiness

Plan 14-02 (Wave 1: state_manager fcntl + v2->v3 migration) and Plan 14-03 (Wave 1: sizing_engine manual_stop precedence) can now spawn — every test class and fixture they reference exists. Plan 14-04 (Wave 2: web/routes/trades.py endpoints) and Plan 14-05 (Wave 2: dashboard HTMX markup) likewise have their entire test surface mapped out.

The TestWebHexBoundary AST walk currently no-ops on web/routes/trades.py (file does not yet exist; the existing `if not py_path.exists(): continue` guard at line 230-232 covers it). When Plan 14-04 lands trades.py, the imports of state_manager, sizing_engine, and system_params inside the file are now legal because the latter two are out of FORBIDDEN_FOR_WEB.

No blockers, no concerns.

---
*Phase: 14-trade-journal-mutation-endpoints*
*Plan: 01*
*Completed: 2026-04-25*
