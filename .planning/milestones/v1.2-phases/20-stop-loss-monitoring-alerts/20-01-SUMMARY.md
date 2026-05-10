---
phase: 20
plan: "01"
subsystem: alerts
tags: [alerts, stop-loss, email, dashboard, state-migration, tdd]
dependency_graph:
  requires: [state_manager, alert_engine, notifier, dashboard, main, sizing_engine]
  provides: [send_stop_alert_email, _evaluate_paper_trade_alerts, _render_alert_badge, last_alert_state schema field]
  affects: [state.json schema (v7), dashboard.html (Alert column), email output]
tech_stack:
  added: [alert_engine.py, tests/test_alert_engine.py, tests/test_notifier_stop_alert.py, tests/test_main_alerts.py, tests/fixtures/state_v7_with_alerts.json]
  patterns: [two-phase commit, hex-boundary pure-math engine, never-crash email dispatch, idempotent schema migration, NaN float self-inequality trick]
key_files:
  created:
    - alert_engine.py
    - tests/test_alert_engine.py
    - tests/test_notifier_stop_alert.py
    - tests/test_main_alerts.py
    - tests/fixtures/state_v7_with_alerts.json
  modified:
    - system_params.py (STATE_SCHEMA_VERSION 6->7)
    - state_manager.py (_migrate_v6_to_v7 + MIGRATIONS[7])
    - notifier.py (send_stop_alert_email + _build_alert_subject + _render_alert_email_html + _render_alert_email_text)
    - main.py (_evaluate_paper_trade_alerts + _is_email_worthy + call site step 9.6)
    - dashboard.py (_render_alert_badge + Alert column + .alert-badge CSS)
    - web/routes/paper_trades.py (edit_paper_trade._apply resets last_alert_state=None)
    - tests/test_signal_engine.py (AST guard extended for alert_engine)
    - tests/test_system_params.py (v7 assertions)
    - tests/test_state_manager.py (TestMigrateV6ToV7)
    - tests/test_dashboard.py (TestRenderAlertBadge)
    - tests/test_web_paper_trades.py (test_edit_resets_last_alert_state)
    - tests/conftest.py (_open_row_v7, client_with_state_v6 default -> v7)
    - tests/fixtures/dashboard/golden.html (regenerated with Alert column)
    - tests/fixtures/dashboard/golden_empty.html (regenerated with colspan=10)
decisions:
  - "D-20 palette: used raw hex (#d4edda/#155724 CLEAR, #fff3cd/#856404 APPROACHING, #f8d7da/#721c24 HIT, #e9ecef/#6c757d none) because CSS vars --color-success/warning/danger/muted are absent from _INLINE_CSS"
  - "NaN detection in notifier.py uses x != x float self-inequality trick to avoid adding import math (maintains import count invariant)"
  - "APPROACHING->CLEAR is NOT email-worthy but IS persisted via no_op_writes (badge color refresh)"
  - "Two-phase commit: transitioning rows committed only when emailed=True; no_op_writes committed unconditionally"
metrics:
  duration: "~3h"
  completed: "2026-04-30"
  tasks_completed: 7
  files_changed: 16
  new_tests: 88
---

# Phase 20 Plan 01: Stop-loss Monitoring & Alerts Summary

Stop-loss alert monitoring end-to-end: schema migration v6->v7, pure-math alert engine, batched email via Resend, two-phase commit orchestrator in main.py, dashboard Alert column with colored badges, and edit-reset wiring.

## What Was Built

**alert_engine.py** — Pure-math module (no I/O, stdlib-only: `math`, `typing`). Two functions:
- `compute_alert_state(side, today_low, today_high, today_close, stop_price, atr) -> str` — returns `HIT`/`APPROACHING`/`CLEAR` with HIT-precedence ordering and NaN/atr<=0 guards
- `compute_atr_distance(today_close, stop_price, atr) -> float` — returns `abs(close-stop)/atr` for email distance text

**state_manager.py** — `_migrate_v6_to_v7` backfills `last_alert_state=None` on all existing `paper_trades[]` rows idempotently. Dispatched via `MIGRATIONS[7]`.

**notifier.py** — Three private helpers + one public function:
- `_build_alert_subject(transitions)`: N=1 → `[!stop] INSTRUMENT SIDE STATE — id`; N>1 → `[!stop] N transition(s) in today's paper trades`
- `_render_alert_email_html(transitions, dashboard_url)`: HTML table with inline `style="..."` attributes (Gmail mobile constraint per UAT-16-B)
- `_render_alert_email_text(transitions, dashboard_url)`: plain-text fallback
- `send_stop_alert_email(transitions, dashboard_url) -> bool`: never-crash, empty→False, missing env→False

**main.py** — `_is_email_worthy(old_state, new_state)` classifier and `_evaluate_paper_trade_alerts(state, dashboard_url) -> dict` two-phase commit orchestrator:
- Phase A: iterate open paper_trades, compute new_state via alert_engine, classify into `transitions` (email-worthy) vs `no_op_writes` (not email-worthy but persist)
- Phase B: call `send_stop_alert_email` if transitions non-empty; commit transitions only if `emailed=True` (D-06 rollback); commit no_op_writes unconditionally
- Call site added at step 9.6 in `run_daily_check`, after `mutate_state(_apply_daily_run)` (D-18 non-reentrancy)

**dashboard.py** — `_render_alert_badge(state, has_stop) -> str` renders `<span class="alert-badge alert-{state}">` with CSS classes. `.alert-badge` + `.alert-{clear,approaching,hit,none}` CSS block added. Open trades table extended from 9 to 10 columns with Alert as column 8.

**web/routes/paper_trades.py** — `edit_paper_trade._apply` now sets `row['last_alert_state'] = None` on PATCH so next daily run recomputes (D-09 reset on stop edit).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fixtures used spi_low=8050.0 with stop_price=8100.0 — triggers HIT not intended CLEAR/APPROACHING**
- **Found during:** Task 5 GREEN (test_main_alerts.py)
- **Issue:** Multiple tests in `TestEvaluatePaperTradeAlerts` intended to produce CLEAR or APPROACHING but used default `spi_low=8050.0` (below `stop_price=8100.0`). For LONG side, `today_low <= stop_price` triggers HIT per D-10. Comments in test said "low=8050 > stop=8100" which is arithmetically false.
- **Fix:** Changed `spi_low=8050.0` to `spi_low=8110.0` (above stop=8100) in 6 test fixtures: `test_initial_none_to_clear_no_email`, `test_initial_none_to_approaching_emails`, `test_clear_to_clear_no_email`, `test_clear_to_approaching_emails`, `test_approaching_to_clear_no_email`, `test_approaching_to_approaching_dedup_no_email`, `test_send_success_commits`.
- **Files modified:** `tests/test_main_alerts.py`
- **Commit:** d067acb

**2. [Rule 1 - Bug] Pre-existing TestMigrateV5ToV6 assertions hard-coded == 6 broke after v7 migration added**
- **Found during:** Task 1 GREEN (state_manager.py)
- **Issue:** `_migrate()` walker advances to STATE_SCHEMA_VERSION (now 7); tests asserting `== 6` failed.
- **Fix:** Updated assertions to `== STATE_SCHEMA_VERSION` (forward-compatible).
- **Files modified:** `tests/test_state_manager.py`
- **Commit:** 538e3c6

## D-20 Palette Decision

CSS vars `--color-success`, `--color-warning`, `--color-danger`, `--color-muted` are **absent** from `_INLINE_CSS`. Used raw hex from D-14 verbatim:
- CLEAR: `#d4edda` / `#155724`
- APPROACHING: `#fff3cd` / `#856404`
- HIT: `#f8d7da` / `#721c24`
- none: `#e9ecef` / `#6c757d`

## Known Stubs

None — all functions are fully wired. `send_stop_alert_email` calls the real Resend API via `_post_to_resend`. `_evaluate_paper_trade_alerts` uses real `mutate_state` with fcntl locking. Dashboard Alert column reads `last_alert_state` directly off paper_trades rows.

## Self-Check: PASSED
