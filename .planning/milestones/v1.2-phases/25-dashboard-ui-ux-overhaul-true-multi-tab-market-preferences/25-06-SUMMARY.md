---
phase: 25
plan: "06"
subsystem: dashboard-status-strip
tags: [status-strip, or-01, or-02, awst, htmx, countdown, wave-3]
dependency_graph:
  requires: [25-02, 25-04]
  provides:
    - "render_status_strip(state, now_awst) -> str in dashboard_renderer/components/header.py"
    - "_derive_status_dot_class(state, now_awst) -> (css_class, status_text) per OR-01"
    - "_compute_next_awst_0800(now_awst) helper"
    - "_format_countdown_text(now_awst, target_awst) OR-02 format"
    - "GET /status-strip real handler (auth-gated, no-store cache)"
    - "_STATUS_STRIP_REFRESH_JS 08:01 AWST one-shot timer in shell.py"
  affects:
    - "All dashboard pages (header now includes status strip)"
    - "Golden HTML snapshots regenerated"
tech_stack:
  added: []
  patterns:
    - "OR-01 3-state derivation: success/stale/failure/never from state['last_run'] + state['warnings']"
    - "OR-02 countdown format: >24h shows day+time+AWST, <24h shows Nh Mm, <1h shows NNm"
    - "Static '08:00 AWST' prefix outside countdown span ensures AWST literal always in rendered HTML"
    - "Weekend handling: Sat/Sun inherit Friday's status (no daemon run expected on weekends)"
    - "08:01 AWST one-shot refresh via setTimeout targeting 00:01 UTC; re-arms daily"
key_files:
  created: []
  modified:
    - "dashboard_renderer/formatters.py — _derive_status_dot_class, _compute_next_awst_0800, _format_countdown_text added"
    - "dashboard_renderer/components/header.py — render_status_strip() added; render_header() calls it"
    - "dashboard_renderer/shell.py — _STATUS_STRIP_REFRESH_JS added; emitted after _AWST_COUNTDOWN_JS"
    - "web/routes/dashboard.py — /status-strip stub replaced with real handler"
    - "tests/test_dashboard.py — xfail removed from 2 TestPhase25Countdown tests; TestPhase25StatusDotDerivation (7 parametrised rows) added"
    - "tests/test_web_dashboard.py — xfail removed + r.text bug fixed in test_status_strip_unauthed_returns_401_or_403"
    - "tests/fixtures/dashboard/golden.html — regenerated with strip in header"
    - "tests/fixtures/dashboard/golden_empty.html — regenerated from reset_state() with strip"
    - "dashboard-signals.html, dashboard-account.html, dashboard-settings.html, dashboard-market-test.html — regenerated sibling pages"
decisions:
  - "Static '08:00 AWST · ' prefix outside the [data-countdown] span so AWST literal is always in server HTML regardless of countdown magnitude"
  - "Weekend OR-01: Sat inherits Friday (days_diff <= 1), Sun inherits Friday (days_diff <= 2); formula is weekday - 4"
  - "warning text NOT rendered in strip output (T-25-06-01 info-disclosure mitigation — only state class emitted)"
  - "golden_empty.html regenerated from state_manager.reset_state() not empty_state.json (same issue as Plan 05 deviation #2)"
metrics:
  duration: ~30min
  completed: "2026-05-05"
  tasks: 2
  files: 13
---

# Phase 25 Plan 06: Status Strip Summary

JWT-style OR-01 3-state status dot derivation + OR-02 countdown format implemented as server-rendered strip with HTMX auto-refresh at 08:01 AWST and on visibilitychange.

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-05-05
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments

**Task 1 — Helpers + render_status_strip:**

- Added to `dashboard_renderer/formatters.py`:
  - `_derive_status_dot_class(state, now_awst)` — OR-01 truth table: never/success/stale/failure CSS classes
  - `_compute_next_awst_0800(now_awst)` — next Mon-Fri 08:00 AWST target datetime
  - `_format_countdown_text(now_awst, target_awst)` — OR-02 format (>24h: `Mon 08:00 AWST · in 2d 16h`; <24h: `in Nh Mm`; <1h: `in NNm`)
- Added `render_status_strip(state, now_awst)` to `dashboard_renderer/components/header.py`
- Updated `render_header()` to include the strip as a sibling to the existing meta block
- Strip emits `id="status-strip"`, `hx-get="/status-strip"`, `hx-trigger="refresh, visibilitychange..."`, `hx-swap="outerHTML"`, `aria-live="polite"`
- Static `08:00 AWST ·` prefix ensures AWST literal always present in rendered HTML

**Task 2 — Endpoint + JS + tests:**

- Replaced `/status-strip` stub in `web/routes/dashboard.py` with real handler:
  - Loads state, resolves `datetime.now(Perth)`, calls `render_status_strip`
  - `Cache-Control: no-store, private` (T-25-06-03)
  - Auth-gated by existing `AuthMiddleware` (NOT in PUBLIC_PATHS)
- Added `_STATUS_STRIP_REFRESH_JS` to `dashboard_renderer/shell.py` — schedules 08:01 AWST one-shot `htmx.trigger(el, 'refresh')` via `setTimeout(msToNext0801Utc())`, re-arms daily
- Flipped xfail on `TestPhase25Countdown::test_status_strip_present_in_header` and `::test_status_strip_first_run_shows_awaiting`
- Fixed `r.text` → `resp.text` bug in `test_status_strip_unauthed_returns_401_or_403` + flipped xfail
- Added `TestPhase25StatusDotDerivation` with 7 parametrised rows covering all OR-01 branches (no xfail)
- Regenerated `golden.html` and `golden_empty.html` (strip now in header)

**Test gate status:**

- `TestPhase25StatusStripEndpoint`: 3/3 PASS (xfail removed from all three)
- `TestPhase25Countdown`: 3/3 PASS (xfail removed from 2)
- `TestPhase25StatusDotDerivation`: 7/7 PASS
- Full suite: 291 passed, 17 xfailed, 0 failed

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1+2 | Status strip helpers + endpoint + tests (atomic) | 404fe1e | dashboard_renderer/formatters.py, header.py, shell.py, web/routes/dashboard.py, tests/test_dashboard.py, tests/test_web_dashboard.py, golden.html, golden_empty.html, 4x sibling pages |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Static AWST literal needed outside countdown span**

- **Found during:** Task 1 verification
- **Issue:** Plan action placed all countdown text inside `[data-countdown]` span. For gaps <24h, OR-02 format is `in Nh Mm` — no "AWST" in the text. Plan's verify assertion `assert 'AWST' in strip` would fail for that case.
- **Fix:** Emitted `<span class="next-run">08:00 AWST · <span data-countdown="...">in Nh Mm</span></span>` — static `08:00 AWST ·` prefix is always rendered server-side; JS only updates the inner ticker span.
- **Files modified:** dashboard_renderer/components/header.py
- **Commit:** 404fe1e

**2. [Rule 1 - Bug] golden_empty.html regeneration used wrong fixture (same as Plan 05 deviation #2)**

- **Found during:** Task 2 test run
- **Issue:** `regenerate_dashboard_golden.py` renders from `empty_state.json` (no markets dict); `TestEmptyState` renders from `state_manager.reset_state()` (has SPI200 + AUDUSD). Golden diverged after strip addition.
- **Fix:** Re-rendered `golden_empty.html` directly from `reset_state()` output in a one-off script invocation.
- **Files modified:** tests/fixtures/dashboard/golden_empty.html
- **Commit:** 404fe1e

**3. [Rule 1 - Bug] r.text NameError in test_status_strip_unauthed_returns_401_or_403**

- **Found during:** Task 2 xfail flip analysis
- **Issue:** Pre-existing typo (`r.text` where `resp` is the variable name); caused NameError inside xfail, masking the real test failure. Plan 04 SUMMARY noted this as "remains xfail" (Plan 06 scope).
- **Fix:** Changed `r.text` → `resp.text`; removed xfail decorator.
- **Files modified:** tests/test_web_dashboard.py
- **Commit:** 404fe1e

## Threat Surface Scan

All three STRIDE mitigations in the plan's threat model implemented:

- T-25-06-01 (info disclosure): `render_status_strip` emits only dot class + status text ("OK"/"Stale"/"Failed"/"Never run") — no `warning.message` interpolation. Verified by inspection of header.py output template.
- T-25-06-02 (auth bypass): `/status-strip` registered under existing dashboard router gated by `AuthMiddleware`. NOT in `PUBLIC_PATHS`. `test_status_strip_unauthed_returns_401_or_403` PASSES.
- T-25-06-03 (cache poisoning): `Cache-Control: no-store, private` header on every `/status-strip` response.

No new trust boundaries introduced beyond the plan's threat model.

## Known Stubs

None — all wiring is complete.

## Self-Check

Files exist:
- `dashboard_renderer/formatters.py` — FOUND (_derive_status_dot_class, _compute_next_awst_0800, _format_countdown_text defined)
- `dashboard_renderer/components/header.py` — FOUND (render_status_strip defined)
- `dashboard_renderer/shell.py` — FOUND (_STATUS_STRIP_REFRESH_JS defined + emitted)
- `web/routes/dashboard.py` — FOUND (real get_status_strip handler, not stub)
- `tests/test_dashboard.py` — FOUND (TestPhase25StatusDotDerivation + xfail removed)
- `tests/test_web_dashboard.py` — FOUND (xfail removed, r.text fixed)

Commits exist:
- `404fe1e` — FOUND

AEST gate: `grep -rn 'AEST' dashboard_renderer/ web/routes/` → 0 lines

## Self-Check: PASSED
