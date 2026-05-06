---
phase: 25
plan: "02"
subsystem: dashboard_renderer
tags: [shell, assets, nav, regen-marker, wave-1-foundation]
dependency_graph:
  requires: []
  provides: [dashboard_renderer.assets, dashboard_renderer.shell, dashboard_renderer.components.nav]
  affects: [dashboard.py, web/routes/dashboard.py]
tech_stack:
  added: []
  patterns: [inline-shell-D02, assets-source-of-truth, interface-stubs]
key_files:
  created:
    - dashboard_renderer/components/nav.py
  modified:
    - dashboard_renderer/assets.py
    - dashboard_renderer/shell.py
    - dashboard.py
    - dashboard_renderer/components/__init__.py
    - web/routes/dashboard.py
    - tests/test_web_dashboard.py
decisions:
  - "assets.py imports color tokens from system_params directly (not via dashboard.py) to break the import cycle"
  - "_INLINE_CSS preserved verbatim — same CSS content, relocated (D-15 rebalance is Plan 09)"
  - "_CHARTJS_SRI/_HTMX_SRI naming preserved from dashboard.py (not renamed to _INTEGRITY) to avoid breaking callers"
  - "Legacy alias names (CHARTJS_URL, INLINE_CSS etc.) retained in assets.py for any out-of-tree consumers"
  - "Test fixtures updated to use new class=tabs-tabs-function marker (Rule 1 bug fix)"
metrics:
  duration: ~20min
  completed: "2026-05-05"
  tasks: 2
  files: 7
---

# Phase 25 Plan 02: Renderer Consolidation Summary

Wave 1 foundation: shell constants migrated to `dashboard_renderer/assets.py` as source of truth; `shell.py` fleshed out; `nav.py` interface stubs created; regen marker updated to force post-deploy refresh of all 5 sibling HTMLs.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Migrate shell constants to assets.py + flesh out shell.py | 32c6dfb | dashboard_renderer/assets.py, dashboard_renderer/shell.py, dashboard.py |
| 2 | Create nav.py stubs + update _REQUIRED_DASHBOARD_MARKER | 9395d1d | dashboard_renderer/components/nav.py, web/routes/dashboard.py |

## What Was Built

**Task 1 — Shell constant migration (D-02):**
- `dashboard_renderer/assets.py` is now the source of truth for all shell constants: `_INLINE_CSS` (16,225 chars), `_HANDLE_TRADES_ERROR_JS`, `_TRACE_TOGGLE_JS`, CDN URLs and SRI hashes for Chart.js 4.4.6, HTMX 1.9.12, htmx-json-enc 1.9.12. Color tokens imported directly from `system_params`.
- `dashboard.py` now re-exports all 9 constants from assets.py (no local definitions for those constants).
- `dashboard_renderer/shell.py` replaced 8-line delegation shim with proper `render_html_shell()` renderer that: (a) imports constants from assets.py; (b) emits the complete `<!DOCTYPE html>` shell; (c) includes the new `_AWST_COUNTDOWN_JS` helper (Phase 25 D-08 — JS-side countdown using fixed UTC+8 offset, never browser TZ).

**Task 2 — Interface stubs + marker change:**
- `dashboard_renderer/components/nav.py` created with three exported functions: `render_function_strip()`, `render_market_strip()`, `render_two_axis_nav()`. D-04 zero-DOM rule implemented: `render_market_strip` returns `''` when `active_function == 'account'`. Plan 25-03 (Wave 2) fills in the full nav HTML.
- `dashboard_renderer/components/__init__.py` re-exports all three nav functions.
- `web/routes/dashboard.py` `_REQUIRED_DASHBOARD_MARKER` updated from `b'<nav class="tabs"'` to `b'class="tabs tabs-function"'`. This token is absent from all 5 existing `dashboard*.html` files, so `_is_stale()` returns True on first request post-deploy — automatic regen of all sibling files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Surgical replacement instead of monolithic block swap**
- **Found during:** Task 1 implementation
- **Issue:** The constant block to relocate contained non-CSS sections (`_INSTRUMENT_DISPLAY_NAMES`, `_CONTRACT_SPECS`, market registry functions, formatters including `_fmt_em_dash`) that should NOT move to assets.py. A monolithic replacement would have deleted these.
- **Fix:** Used four separate surgical replacements targeting only the CDN constants section, `_HANDLE_TRADES_ERROR_JS`, `_INLINE_CSS`, and `_TRACE_TOGGLE_JS` respectively.
- **Files modified:** dashboard.py (implementation), no new files.
- **Commits:** 32c6dfb

**2. [Rule 1 - Bug] Test fixtures used old regen marker**
- **Found during:** Task 2 verification
- **Issue:** Three test HTML strings in `tests/test_web_dashboard.py` used `<nav class="tabs">` to simulate a "fresh" dashboard that should not trigger regen. After the marker changed to `class="tabs tabs-function"`, these fixtures no longer contained the new marker, causing `_is_stale()` to return True and triggering regen on what should be "fresh" HTML.
- **Fix:** Updated all 3 fixture strings to `<nav class="tabs tabs-function">` so staleness tests continue to correctly exercise the D-08 strict-greater-than semantics.
- **Files modified:** tests/test_web_dashboard.py
- **Commit:** 9395d1d

## Pre-existing Out-of-Scope Issues

The following failures exist in the test suite prior to this plan and are unrelated to Plan 25-02 changes:
- `tests/test_deploy_sh.py::TestDeployShSequence::test_step_5_pip_install_requirements_present` — test expects `.venv/bin/pip install` but `deploy.sh` uses `.venv/bin/python -m pip install`. Pre-existing mismatch, out of scope per deviation rules scope boundary.
- `tests/test_deploy_sh.py::TestDeployShSequence::test_order_pull_before_pip` — ordering test that depends on the above.
- `tests/test_deploy_sh.py::TestDeployShSequence::test_order_pip_before_systemctl` — same dependency chain.

These are logged to deferred-items.

## Test Results

- **Before:** 237 passed, 30 xfailed
- **After:** 1728 passed, 40 xfailed, 3 pre-existing failures (test_deploy_sh, unrelated to Plan 25-02)
- All Plan 25-02 functionality tests green.

## Threat Flags

None. Plan 25-02 is a pure constant relocation with no new network surface. T-25-02-01 (XSS via market_id in nav.py implementation) documented in plan; stub contains no user-controlled output.

## Known Stubs

- `dashboard_renderer/components/nav.py::render_function_strip` — returns empty `<nav>` with TODO comment. Wired in Plan 25-03.
- `dashboard_renderer/components/nav.py::render_market_strip` — returns empty `<nav>` with TODO comment (or `''` for account). Wired in Plan 25-03.

These stubs are intentional for Wave 1; Plan 25-03 (Wave 2) implements the full nav body.

## Self-Check

- [x] `dashboard_renderer/assets.py` contains actual constant definitions (not re-exports)
- [x] `dashboard_renderer/shell.py` emits complete HTML shell using assets.py imports
- [x] `dashboard.py` re-exports constants from assets.py (no local definitions)
- [x] `dashboard_renderer/components/nav.py` exists with three exported functions
- [x] D-04: `render_market_strip({}, '', 'account') == ''`
- [x] `_REQUIRED_DASHBOARD_MARKER` updated to Phase-25 token
- [x] New marker absent from existing `dashboard.html` (regen will be triggered post-deploy)
- [x] Task 1 commit: 32c6dfb
- [x] Task 2 commit: 9395d1d

## Self-Check: PASSED
