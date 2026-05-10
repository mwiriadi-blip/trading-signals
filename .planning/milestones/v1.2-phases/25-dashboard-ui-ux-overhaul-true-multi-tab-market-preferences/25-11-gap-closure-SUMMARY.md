---
phase: 25
plan: 25-11
title: Gap closure — D-14 placeholders + 3 D-11 test repairs
subsystem: dashboard-renderer
tags: [gap-closure, test-repair, security, ux, placeholder]
dependency_graph:
  requires: [25-07-empty-state-collapse, 25-08-settings-fieldsets]
  provides: [D-14-placeholder-inheritance, D-11-test-suite-green]
  affects: [dashboard_renderer/components/settings.py, tests/test_dashboard.py]
tech_stack:
  added: []
  patterns:
    - D-14 placeholder inheritance via _strategy_settings_for(state, first_market_id)
    - golden snapshot regeneration after component changes
key_files:
  created: []
  modified:
    - dashboard_renderer/components/settings.py
    - tests/test_dashboard.py
    - tests/fixtures/dashboard/golden_empty.html
    - tests/fixtures/dashboard/golden.html
    - tests/fixtures/dashboard/empty_state.json
decisions:
  - "D-14 placeholders sourced from first market's Settings; uses _strategy_settings_for which merges DEFAULT_STRATEGY_SETTINGS"
  - "7 override fields in Market Test: ADX, votes, risk_long, risk_short, atr_long, atr_short, contract_cap"
  - "XSS test </script> count updated 5→6 to reflect Phase 25 keyboard/ARIA JS block addition"
  - "empty_state.json updated to match current reset_state() — adds markets, strategy_settings, initial_account, contracts keys"
metrics:
  duration: ~20min
  completed: 2026-05-06T02:49:14Z
  tasks_completed: 4
  tasks_total: 4
  files_modified: 5
---

# Phase 25 Plan 11: Gap Closure — D-14 Placeholders + 3 D-11 Test Repairs Summary

Closed all 4 gaps surfaced by 25-VERIFICATION.md. Phase 25 test suite now at 313 pass, 0 fail.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 2 | Repair `test_chart_payload_escapes_script_close` — seed ≥5 equity entries, update `</script>` count 5→6 | 8f62f1b |
| 3 | Update `test_equity_chart_empty_state_placeholder` to post-D-11 copy | 8f62f1b |
| 4 | Regenerate `tests/golden_empty.html` — update `empty_state.json` then regen both goldens | b33d67c |
| 1 | Wire D-14 Market Test placeholder inheritance + `TestPhase25MarketTestPlaceholders` | aa594f2 |

## Decisions Made

- **D-14 placeholder source:** `_strategy_settings_for(state, first_market_id)` — uses insertion-order first market, merging with `DEFAULT_STRATEGY_SETTINGS`. This is the same logic used by the Settings tab renderer, consistent with how "inherited defaults" are computed throughout the codebase.

- **7 override fields wired:** ADX gate, momentum votes, long risk %, short risk %, long ATR multiple, short ATR multiple, contract cap. Matches the plan acceptance criterion of ≥7 `placeholder=` matches in `render_market_test_tab`.

- **XSS test `</script>` count:** Updated from 5 to 6. Phase 25 added a keyboard/ARIA sync JS block (`_DETAILS_ARIA_SYNC_JS` + tabs keyboard JS) that adds one more `</script>` close tag to the shell. The injection defense itself was verified working (escaped form `<\/script>` present in chart payload).

- **golden regen approach:** `empty_state.json` was stale (missing `markets`, `strategy_settings`, `initial_account`, `contracts` keys from post-Phase-25 `reset_state()`). Updated fixture first, then ran `regenerate_dashboard_golden.py` to produce both goldens from the correct state shape.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Golden regen needed two passes**
- **Found during:** Task 4 (then again after Task 1 changed settings.py)
- **Issue:** `regenerate_dashboard_golden.py` uses static `empty_state.json` but test uses `state_manager.reset_state()`. The JSON was stale — 4 keys missing. After Task 1 added new form fields to `render_market_test_tab`, both golden files drifted again.
- **Fix:** Updated `empty_state.json` to match current `reset_state()` output; included both golden regen passes in the task flow; rolled final golden regen into the Task 1 commit.
- **Files modified:** `tests/fixtures/dashboard/empty_state.json`, `tests/fixtures/dashboard/golden_empty.html`, `tests/fixtures/dashboard/golden.html`
- **Commits:** b33d67c, aa594f2

**2. [Rule 1 - Bug] XSS test `</script>` count was 5, now 6**
- **Found during:** Task 2
- **Issue:** Test asserted exactly 5 `</script>` tags. Phase 25 added ARIA/keyboard JS blocks so the actual count when chart renders is 6. The assertion count was stale.
- **Fix:** Updated count assertion in `test_chart_payload_escapes_script_close` to 6 with explanation of each block contributing to the count.
- **Files modified:** `tests/test_dashboard.py`
- **Commit:** 8f62f1b

## Known Stubs

None. All placeholder values are sourced from live state via `_strategy_settings_for`. Empty `strategy_settings` falls back to `DEFAULT_STRATEGY_SETTINGS` (same as the rest of the codebase).

## Threat Flags

None. No new network endpoints, auth paths, or trust boundaries introduced.

## Self-Check

- [x] `dashboard_renderer/components/settings.py` — `render_market_test_tab()` has 7 `placeholder=` input attrs
- [x] `tests/test_dashboard.py` — `TestPhase25MarketTestPlaceholders` class with 2 methods appended
- [x] `tests/fixtures/dashboard/golden_empty.html` — regenerated, 49702 bytes
- [x] `tests/fixtures/dashboard/golden.html` — regenerated, 66974 bytes
- [x] `tests/fixtures/dashboard/empty_state.json` — updated with current `reset_state()` shape
- [x] Commits 8f62f1b, b33d67c, aa594f2 exist in git log
- [x] `.venv/bin/pytest tests/test_dashboard.py tests/test_web_app_factory.py tests/test_web_dashboard.py -q` → 313 passed, 0 failed

## Self-Check: PASSED
