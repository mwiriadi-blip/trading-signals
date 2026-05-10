---
phase: 23
plan: 07
subsystem: backtest-web-routes
tags: [web, fastapi, path-traversal, input-validation, cookie-auth, BACKTEST-03, BACKTEST-04]
status: complete
---

## Summary

Implemented `web/routes/backtest.py` — the FastAPI adapter mounting /backtest GET + /backtest/run POST. Replaced the Wave 0 NotImplementedError skeleton with the full 4-route adapter and 6 test classes (21 tests).

## What Was Built

- **GET /backtest** — renders latest report by mtime; empty-state D-17 copy when no files exist
- **GET /backtest?history=true** — history view with table + overlay chart (D-06)
- **GET /backtest?run=\<file\>** — specific report with path-traversal defence (T-23-traversal)
- **POST /backtest/run** — operator override form, validates inputs (T-23-input), runs via `backtest.cli.run_backtest`, 303 redirect (not 307)
- All routes auth-gated by Phase 16.1 cookie-session middleware (T-23-auth)

## Key Files

### Created/Modified
- `web/routes/backtest.py` — 224 LOC, 4 routes + path-traversal + input validation
- `tests/test_web_backtest.py` — 6 test classes, 21 tests

## Test Results

| Class | Tests | Threat | Status |
|-------|-------|--------|--------|
| TestGetBacktest | 3 | — | PASS |
| TestPathTraversal | 5 | T-23-traversal | PASS |
| TestPostRun | 7 | T-23-input | PASS |
| TestCookieAuth | 3 | T-23-auth | PASS |
| TestHistoryView | 3 | — | PASS |
| TestPerformanceBudget | 1 | D-14 | PASS |

## Self-Check: PASSED

- [x] All 4 routes wired and responding
- [x] Path-traversal defence: regex + os.listdir whitelist (5 tests)
- [x] Input validation: account>0, costs>=0 (7 tests)
- [x] Cookie auth: browser→302, curl→401, POST→401 (3 tests)
- [x] D-14 performance-budget docstring + regression guard test
- [x] Hex-boundary: no signal_engine/sizing_engine imports in web layer
- [x] 303 redirect (not 307) for POST→GET pattern
- [x] Empty-state D-17 copy when no backtest files exist
- [x] Full suite: 515 passed (1 pre-existing nginx test failure unrelated to Phase 23)

## Deviations

None. Implementation matches plan exactly.
