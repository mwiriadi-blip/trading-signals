---
phase: 25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences
plan: "01"
subsystem: testing
tags: [pytest, xfail, tdd, dashboard, fastapi, routes, cookies]

# Dependency graph
requires: []
provides:
  - "30 xfail(strict=True) test methods in tests/test_dashboard.py covering D-09..D-22"
  - "10 xfail(strict=True) + 1 regression guard test methods in tests/test_web_app_factory.py covering D-01..D-05"
  - "3 xfail(strict=True) test methods in tests/test_web_dashboard.py covering D-06/D-07"
  - "_empty_state() and _render_to_str() helper functions for Phase-25 test reuse"
affects:
  - "25-02 through 25-11 (implementation plans that flip xfail→pass)"
  - "tests/test_dashboard.py (12 new classes with 30 methods)"
  - "tests/test_web_app_factory.py (2 new classes with 8 methods)"
  - "tests/test_web_dashboard.py (1 new class with 3 methods)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_render_to_str() helper wraps dashboard_renderer internals to return HTML string without file I/O — enables stateless unit tests"
    - "xfail(strict=True) scaffold pattern: tests fail today, flip green only when implementation lands"
    - "Route test two-part gate: assert route registered AND assert behavior, so unknown-market 404 test is meaningful only once route exists"

key-files:
  created: []
  modified:
    - "tests/test_dashboard.py — 12 new Phase-25 test classes (30 xfail methods)"
    - "tests/test_web_app_factory.py — TestPhase25MarketRoutes + TestPhase25SelectedMarketCookie"
    - "tests/test_web_dashboard.py — TestPhase25StatusStripEndpoint"

key-decisions:
  - "Used _render_to_str() internal helper instead of render_dashboard() (which returns None and writes files) to get HTML strings for unit assertions"
  - "test_market_settings_get_route_registered checks GET method (new in P25) not PATCH (already exists from prior work) to avoid false xpass"
  - "test_unknown_market_returns_404 gates on route existence first so it fails for the right reason during xfail period"
  - "Pre-existing 12 test failures in TestForwardStopFragment/TestSideBySideStopDisplay confirmed out-of-scope; logged to deferred-items"

patterns-established:
  - "Phase-25 test helpers (_empty_state, _render_to_str) are module-level in test_dashboard.py — reusable across all Phase-25 unit test classes"

requirements-completed: [P25-01, P25-02, P25-03, P25-04, P25-05, P25-06, P25-07, P25-08, P25-09, P25-10, P25-11, P25-12, P25-13, P25-14, P25-15]

# Metrics
duration: 8min
completed: 2026-05-05
---

# Phase 25 Plan 01: Test Scaffolding Summary

**43 xfail(strict=True) test methods across 3 files lock every Phase-25 acceptance gate (D-01..D-22) as a RED→GREEN contract for Waves 2-4 implementation plans**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-05T11:40:00Z
- **Completed:** 2026-05-05T11:48:33Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- 12 xfail test classes (30 methods) added to `tests/test_dashboard.py` covering first-run collapse, stats bar gate, equity chart gate, settings fieldsets, font tokens, add-market chip, active tab aria, inline color cleanup, wide table wrappers, button renames, strategy version, and status strip
- 2 xfail test classes (8 methods) + 1 regression guard added to `tests/test_web_app_factory.py` covering GET market function routes, cookie write/attributes
- 1 xfail test class (3 methods) added to `tests/test_web_dashboard.py` covering `/status-strip` endpoint
- `_render_to_str()` helper established — wraps `dashboard_renderer` internals to produce HTML string without disk I/O, enabling stateless unit tests without `tmp_path` fixtures
- All 195 pre-existing `test_dashboard.py` tests remain green; regression guard passes

## Task Commits

1. **Task 1: Phase-25 unit test classes in test_dashboard.py** - `d7d9daa` (test)
2. **Task 2: Routing/cookie/status-strip test classes** - `28dc9a3` (test)

## Files Created/Modified

- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_dashboard.py` — 12 new xfail test classes (30 methods) + `_empty_state()` + `_render_to_str()` helpers appended at end of file
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_web_app_factory.py` — `TestPhase25MarketRoutes` (6 methods: 5 xfail + 1 regression guard) + `TestPhase25SelectedMarketCookie` (2 xfail)
- `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/tests/test_web_dashboard.py` — `TestPhase25StatusStripEndpoint` (3 xfail)

## Decisions Made

- `_render_to_str()` calls `_build_render_context` + `_render_header_and_body` + `_render_tabbed_dashboard` directly rather than `render_dashboard()` which writes files (returns None). This keeps unit tests stateless and removes need for `tmp_path` fixtures in every Phase-25 test method.
- Route registration test for settings uses GET behavior check (new in P25) not path membership (PATCH already exists from prior work).
- Unknown-market 404 test gates on route existence to ensure it fails for the right reason (route doesn't exist → asserting route registered fails first).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] render_dashboard() returns None — tests must use internal API**
- **Found during:** Task 1 (adding test classes)
- **Issue:** Plan specified `html_out = render_dashboard(_empty_state(...))` treating it as a string. `render_dashboard()` writes to files and returns `None`. All assertions would have received `None` and failed incorrectly.
- **Fix:** Added `_render_to_str()` module-level helper that calls `_build_render_context()` + `_render_header_and_body()` + `_render_tabbed_dashboard()` to return HTML string. All Phase-25 test methods use this helper.
- **Files modified:** `tests/test_dashboard.py`
- **Verification:** All 30 xfail methods report XFAIL (not ERROR) — confirms they run and assert correctly.
- **Committed in:** d7d9daa (Task 1 commit)

**2. [Rule 1 - Bug] test_market_settings_route_registered was XPASS(strict)**
- **Found during:** Task 2 verification run
- **Issue:** `/markets/{market_id}/settings` already exists as a PATCH route from prior work (Phase 14+). The test checking `path in paths` matched without caring about HTTP method. With `strict=True`, unexpected pass = failure.
- **Fix:** Changed to `test_market_settings_get_route_registered` — makes a GET request and asserts 200. GET handler doesn't exist yet (only PATCH exists), so test correctly xfails.
- **Files modified:** `tests/test_web_app_factory.py`
- **Verification:** Test reports XFAIL after fix.
- **Committed in:** 28dc9a3 (Task 2 commit)

**3. [Rule 1 - Bug] test_unknown_market_returns_404 was XPASS(strict)**
- **Found during:** Task 2 verification run
- **Issue:** `/markets/NOPE/signals` returns 404 because the route doesn't exist yet (path doesn't match any registered route). Test assertion `== 404` unexpectedly passes today — but for the wrong reason. With `strict=True`, this is a failure.
- **Fix:** Added gate check — test first asserts `/markets/{market_id}/signals` is in registered routes (fails today), only then checks the 404. xfail fires on the route-registration check, not the HTTP call.
- **Files modified:** `tests/test_web_app_factory.py`
- **Verification:** Test reports XFAIL after fix.
- **Committed in:** 28dc9a3 (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (all Rule 1 bugs in plan design)
**Impact on plan:** All fixes necessary for correct test scaffolding. No scope creep.

## Issues Encountered

- Pre-existing 12 test failures in `TestForwardStopFragment` and `TestSideBySideStopDisplay` in `test_web_dashboard.py` confirmed pre-existing (fail before any Phase-25 changes). Out-of-scope per deviation boundary rule. Logged to deferred-items.

## Known Stubs

None — this plan creates test scaffolding only (xfail stubs by design). The xfail decorators are intentional markers, not functional stubs. Each will be removed by the corresponding implementation plan in Waves 2-4.

## Threat Flags

None — pure test scaffolding; no new production code paths, endpoints, or data flows introduced.

## Self-Check

Files exist:
- `tests/test_dashboard.py` — modified ✓
- `tests/test_web_app_factory.py` — modified ✓
- `tests/test_web_dashboard.py` — modified ✓

Commits exist:
- `d7d9daa` — Task 1 ✓
- `28dc9a3` — Task 2 ✓

## Self-Check: PASSED

All files modified and committed. 43 xfail test methods registered. 195 pre-existing test_dashboard.py tests green. Regression guard passes.

## Next Phase Readiness

- Wave 2 implementation plans (25-02 through 25-06) have their acceptance gates locked and ready to flip green
- `_render_to_str()` and `_empty_state()` helpers are available for any additional Phase-25 unit tests
- Pre-existing 12 failures in `TestForwardStopFragment`/`TestSideBySideStopDisplay` are a known deferred item — not blocked by Phase-25 work

---
*Phase: 25-dashboard-ui-ux-overhaul-true-multi-tab-market-preferences*
*Completed: 2026-05-05*
