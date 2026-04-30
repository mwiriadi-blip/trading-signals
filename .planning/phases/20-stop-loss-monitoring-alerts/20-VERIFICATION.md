---
phase: 20-stop-loss-monitoring-alerts
verified: 2026-04-30T00:00:00Z
status: passed
score: 30/30 must-haves verified
overrides_applied: 0
---

# Phase 20: Stop-Loss Monitoring & Alerts — Verification Report

**Phase Goal:** Daily-run alert evaluator detects state transitions for open paper trades with non-null stop_price. Sends batched `[!stop]` email (HTML + plain text) on transitions only. Dashboard renders Alert column with colored badges. Two-phase commit pattern outside `mutate_state(_apply_daily_run)` closure (G-45 / planner D-18). Schema bump 6→7 + `_migrate_v6_to_v7` adds `last_alert_state: None` field. Edit resets `last_alert_state`.
**Verified:** 2026-04-30
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP SC-1..6 + PLAN must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | On every daily run, system computes CLEAR/APPROACHING/HIT per open trade with non-null stop_price | VERIFIED | `compute_alert_state` in `alert_engine.py`; `_evaluate_paper_trade_alerts` iterates `state['paper_trades']` filtering `status=open` and `stop_price is not None` |
| 2 | SC-2: CLEAR→APPROACHING or *→HIT triggers `[!stop]`-prefixed email | VERIFIED | `_is_email_worthy` + `send_stop_alert_email`; subject prefix `[!stop]` in `_build_alert_subject` |
| 3 | SC-3: Same state on consecutive days does NOT re-trigger email (dedup via `last_alert_state`) | VERIFIED | `if old_state == new_state: continue` in `_evaluate_paper_trade_alerts`; test `test_approaching_to_approaching_dedup_no_email` PASS |
| 4 | SC-4: Dashboard renders "Alerts" pane with CLEAR/APPROACHING/HIT per open trade row, green/amber/red | VERIFIED | `_render_alert_badge` in `dashboard.py`; CSS `.alert-clear/#d4edda`, `.alert-approaching/#fff3cd`, `.alert-hit/#f8d7da`; `test_open_trades_row_renders_badge` PASS |
| 5 | SC-5: APPROACHING uses 0.5×ATR(14); HIT uses today's Low (LONG) or High (SHORT) | VERIFIED | `alert_engine.py:56-61`; HIT checked before APPROACHING; `TestComputeAlertState` 26 test cases PASS |
| 6 | SC-6: Alert-send failures NEVER crash the daily run | VERIFIED | `send_stop_alert_email` returns `bool` never raises; wrapped in `try/except Exception` at call site `main.py:1561-1564`; `test_send_failure_rollback` PASS |
| 7 | STATE_SCHEMA_VERSION = 7 | VERIFIED | `system_params.py:121` — `STATE_SCHEMA_VERSION: int = 7` |
| 8 | MIGRATIONS[7] = _migrate_v6_to_v7 registered between key 6 and close of table | VERIFIED | `state_manager.py:254` — `7: _migrate_v6_to_v7` |
| 9 | _migrate_v6_to_v7 backfills `last_alert_state=None` on existing rows; idempotent | VERIFIED | `state_manager.py:229-251`; `TestMigrateV6ToV7` (7 tests) PASS — backfill, idempotent, preserves-other-fields, skips non-dict rows, no-paper_trades key, silent (no log), full v0→v7 walk |
| 10 | alert_engine.py pure-math: only `math` + `typing`; no I/O, no datetime, no os | VERIFIED | `alert_engine.py:18-22` — `from __future__ import annotations; import math; from typing import Literal`; AST guard `test_forbidden_imports_absent[module_path4]` PASS |
| 11 | compute_alert_state: HIT precedence, APPROACHING threshold, CLEAR default, NaN/atr<=0 safe | VERIFIED | `alert_engine.py:51-62`; NaN guard first; HIT before APPROACHING; `TestComputeAlertState` 26 cases PASS; behavioral spot-check PASS |
| 12 | compute_atr_distance returns NaN on atr<=0 or any NaN input | VERIFIED | `alert_engine.py:71-75`; behavioral spot-check PASS |
| 13 | send_stop_alert_email returns bool, never raises, empty→False without calling Resend | VERIFIED | `notifier.py:1910-1911` — `if not transitions: return False`; `TestSendStopAlertEmail` PASS |
| 14 | send_stop_alert_email passes BOTH html_body AND text_body to _post_to_resend | VERIFIED | `notifier.py:1925-1931` — both passed; `test_html_text_parity_every_transition_id_in_both` PASS |
| 15 | N==1 subject names INSTRUMENT SIDE STATE id; N>1 batched count format | VERIFIED | `_build_alert_subject` lines 1783-1790; `test_n_one_transition_subject_format` + `test_n_three_transitions_subject_format` PASS |
| 16 | XSS: every string field in html body wrapped in `html.escape(str(v), quote=True)` | VERIFIED | `notifier.py:1811-1817`; `test_html_body_is_html_escaped` asserts `&lt;script&gt;` present and `<script>` absent PASS |
| 17 | HTML+plain-text parity: every transition id AND new_state in BOTH bodies | VERIFIED | `_render_alert_email_text` iterates same `transitions`; `test_html_text_parity_every_transition_id_in_both` PASS |
| 18 | Email badges use inline `style="..."` attributes — no CSS classes (Gmail constraint) | VERIFIED | `notifier.py:1803-1807` — `_BADGE_STYLES` dict with inline style strings; `test_html_body_uses_inline_styles_only` asserts `class="alert-"` NOT in html_body PASS |
| 19 | D-18: `_evaluate_paper_trade_alerts` called AFTER `mutate_state(_apply_daily_run)` returns, BEFORE `_render_dashboard_never_crash` | VERIFIED | `main.py:1542-1572` — mutate_state returns at 1542, alert eval at 1562, dashboard render at 1572; `test_two_phase_commit_ordering_no_deadlock` PASS |
| 20 | Two-phase commit: transitioning rows committed ONLY when emailed=True; no_op_writes committed unconditionally | VERIFIED | `main.py:1113-1129` — two independent `if emailed:` and `commit_map.update(no_op_writes)` branches; `test_send_failure_rollback` asserts transitioning rows NOT committed on failure; `test_approaching_to_clear_no_email` asserts CLEAR persisted without email PASS |
| 21 | APPROACHING→CLEAR NOT email-worthy; badge refreshes via no_op_writes | VERIFIED | `_is_email_worthy` line 1020 returns False when `new_state=='CLEAR'` and `old_state!='HIT'`; `test_approaching_to_clear_no_email` PASS |
| 22 | D-17: ohlc_window reads use lowercase `'low'`, `'high'`, `'close'` keys | VERIFIED | `main.py:1074-1076` — `bar.get('low', float('nan'))`, `bar.get('high', ...)`, `bar.get('close', ...)`; `test_ohlc_window_uses_lowercase_keys` PASS |
| 23 | D-19: dashboard.py does NOT import alert_engine; reads last_alert_state directly off row dict | VERIFIED | `grep -n "^from alert_engine|^import alert_engine" dashboard.py` → zero results; `_render_alert_badge(row.get('last_alert_state'), ...)` at dashboard.py:2396 |
| 24 | D-20 palette: raw hex used (CSS vars absent from _INLINE_CSS) | VERIFIED | SUMMARY documents D-20 decision; `grep "var(--color-success..." dashboard.py` → zero results; hex `.alert-clear {background: #d4edda; color: #155724}` etc. in CSS block |
| 25 | web/routes/paper_trades.py PATCH resets `row['last_alert_state'] = None` on every successful edit | VERIFIED | `paper_trades.py:345` — `row['last_alert_state'] = None`; `test_edit_resets_last_alert_state[None/CLEAR/APPROACHING/HIT]` PASS |
| 26 | ATR NaN/missing: compute_alert_state returns CLEAR; `[Alert] WARN no ATR for <inst>; treating as CLEAR` logged | VERIFIED | `main.py:1068-1070`; `test_atr_nan_treated_as_clear_with_warn_log` PASS |
| 27 | tests/fixtures/state_v7_with_alerts.json exists with schema_version=7, 4 paper_trades rows covering each state × instrument | VERIFIED | Fixture confirmed: schema_version=7, 4 rows: SPI200 None, SPI200 CLEAR, AUDUSD APPROACHING, AUDUSD HIT |
| 28 | G-44 regression: no `enctype="application/json"` in dashboard.py | VERIFIED | `grep -n 'enctype="application/json"' dashboard.py` → zero results |
| 29 | 7 commits with `(20-01)` scope | VERIFIED | `git log --oneline | grep "(20-01)"` → 7 commits: 7d85047, 538e3c6, 0b06a68, 90fdaa5, d067acb, d25cf97, f0012a4 |
| 30 | Pre-existing failures unrelated to Phase 20 | VERIFIED | 12 failures confined to test_nginx_signals_conf.py, test_setup_https_doc.py, test_notifier.py (ruff missing); 1586 passing, all Phase 20 tests green |

**Score:** 30/30 truths verified

---

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `alert_engine.py` | VERIFIED | Pure-math, 76 lines, `compute_alert_state` + `compute_atr_distance` |
| `system_params.py` | VERIFIED | `STATE_SCHEMA_VERSION: int = 7` |
| `state_manager.py` | VERIFIED | `_migrate_v6_to_v7` + `MIGRATIONS[7]` |
| `notifier.py` | VERIFIED | `send_stop_alert_email` + `_build_alert_subject` + `_render_alert_email_html` + `_render_alert_email_text` |
| `main.py` | VERIFIED | `_is_email_worthy` + `_evaluate_paper_trade_alerts` + call site at step 9.6 |
| `dashboard.py` | VERIFIED | `_render_alert_badge` + Alert column + `.alert-badge` CSS block |
| `web/routes/paper_trades.py` | VERIFIED | `row['last_alert_state'] = None` in `edit_paper_trade._apply` |
| `tests/test_signal_engine.py` | VERIFIED | `ALERT_ENGINE_PATH` added to `_HEX_PATHS_ALL` + `_HEX_PATHS_STDLIB_ONLY` |
| `tests/test_state_manager.py` | VERIFIED | `TestMigrateV6ToV7` (7 tests) |
| `tests/test_alert_engine.py` | VERIFIED | `TestComputeAlertState` + `TestComputeAtrDistance` (26 tests) |
| `tests/test_notifier_stop_alert.py` | VERIFIED | `TestSendStopAlertEmail` (full coverage) |
| `tests/test_main_alerts.py` | VERIFIED | `TestEvaluatePaperTradeAlerts` (21 tests) |
| `tests/test_dashboard.py` | VERIFIED | `TestRenderAlertBadge` (11 tests) |
| `tests/test_web_paper_trades.py` | VERIFIED | `test_edit_resets_last_alert_state` parametrized ×4 |
| `tests/fixtures/state_v7_with_alerts.json` | VERIFIED | schema_version=7, 4 rows covering SPI200/AUDUSD × None/CLEAR/APPROACHING/HIT |

---

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `system_params.STATE_SCHEMA_VERSION=7` | `state_manager.MIGRATIONS[7]` | `_migrate` walker advances to `STATE_SCHEMA_VERSION` | WIRED — `7: _migrate_v6_to_v7` at state_manager.py:254 |
| `alert_engine.compute_alert_state` | `main._evaluate_paper_trade_alerts` | `from alert_engine import compute_alert_state, compute_atr_distance` at main.py:43,49 | WIRED |
| `main._evaluate_paper_trade_alerts` | `notifier.send_stop_alert_email` | local import inside function body `main.py:1040` | WIRED |
| `main._evaluate_paper_trade_alerts` | `state_manager.mutate_state(_apply_alert_states)` | second mutate_state call at main.py:1137 | WIRED |
| `run_daily_check` → `_evaluate_paper_trade_alerts` | between mutate_state return and `_render_dashboard_never_crash` | main.py:1542-1572 ordering confirmed | WIRED |
| `web/routes/paper_trades.py edit_paper_trade._apply` | `row['last_alert_state'] = None` | single in-closure line at paper_trades.py:345 | WIRED |
| `dashboard._render_paper_trades_open` | `_render_alert_badge` | call at dashboard.py:2396-2398 | WIRED |
| `tests/test_signal_engine.py _HEX_PATHS_STDLIB_ONLY` | `alert_engine.py` AST walk | `ALERT_ENGINE_PATH` added at lines 482, 597, 600 | WIRED |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `dashboard._render_alert_badge` | `last_alert_state` | paper_trades row dict from state.json (persisted by `_evaluate_paper_trade_alerts`) | Yes — `mutate_state` writes to disk | FLOWING |
| `notifier.send_stop_alert_email` | `transitions` | built by `_evaluate_paper_trade_alerts` from live ohlc_window + indicator_scalars | Yes — real ohlcv bar data | FLOWING |
| email HTML badges | `new_state` per transition | `compute_alert_state(side, low, high, close, stop, atr)` pure-math | Yes — computed from real price data | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `compute_alert_state` NaN guard | `.venv/bin/python3 -c "from alert_engine import compute_alert_state; print(compute_alert_state('LONG', float('nan'), 100, 100, 90, 10))"` | CLEAR | PASS |
| `compute_alert_state` HIT precedence LONG | spot-check in verification run | HIT (low=88 <= stop=90, even with close in range) | PASS |
| `compute_atr_distance` zero ATR | spot-check | float('nan') | PASS |
| `_is_email_worthy` dedup matrix (8 cases) | direct call in verification | All 8 cases match spec | PASS |
| `STATE_SCHEMA_VERSION = 7` | `.venv/bin/python3 -c "import system_params; print(system_params.STATE_SCHEMA_VERSION)"` | 7 | PASS |
| MIGRATIONS[7] registered | `.venv/bin/python3 -c "from state_manager import MIGRATIONS; print(MIGRATIONS[7].__name__)"` | `_migrate_v6_to_v7` | PASS |

---

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| ALERT-01 — Compute HIT/APPROACHING/CLEAR per open trade with stop_price | SATISFIED | `alert_engine.compute_alert_state` + `_evaluate_paper_trade_alerts`; tests PASS |
| ALERT-02 — Send `[!stop]` email on CLEAR→APPROACHING or *→HIT | SATISFIED | `send_stop_alert_email` + `_is_email_worthy`; subject prefix `[!stop]`; tests PASS |
| ALERT-03 — Dedup via `last_alert_state`; no re-send on same state | SATISFIED | Two-phase commit pattern; `old_state == new_state: continue`; dedup tests PASS |
| ALERT-04 — Dashboard "Alerts" pane with CLEAR/APPROACHING/HIT + colored indicator | SATISFIED | `_render_alert_badge` + `.alert-{clear,approaching,hit,none}` CSS; `TestRenderAlertBadge` PASS |

REQUIREMENTS.md status: ALERT-01..04 all marked `[x]` Complete at `| ALERT-01..04 | 20 | Complete |`.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None found | — | — | — |

Scanned: `alert_engine.py`, `notifier.py` (new functions), `main.py` (new functions), `dashboard.py` (new functions), `web/routes/paper_trades.py` (edit reset). No TODOs, no return `{}`, no hardcoded empty data in render paths, no `enctype="application/json"` regression.

---

### Dedup Matrix Coverage

| Transition | Email? | No-op write? | Test |
|-----------|--------|-------------|------|
| None → CLEAR | No | Yes (idempotent) | `test_initial_none_to_clear_no_email` PASS |
| None → APPROACHING | Yes | — | `test_initial_none_to_approaching_emails` PASS |
| None → HIT | Yes | — | `test_initial_none_to_hit_emails` PASS |
| CLEAR → APPROACHING | Yes | — | `test_clear_to_approaching_emails` PASS |
| CLEAR → HIT | Yes | — | `test_clear_to_hit_emails` PASS |
| APPROACHING → APPROACHING | No (dedup) | No write | `test_approaching_to_approaching_dedup_no_email` PASS |
| APPROACHING → HIT | Yes | — | `test_approaching_to_hit_emails` PASS |
| APPROACHING → CLEAR | No | Yes (badge refresh) | `test_approaching_to_clear_no_email` PASS |
| CLEAR → CLEAR | No (dedup) | No write | `test_clear_to_clear_no_email` PASS |
| HIT → HIT | No (dedup) | No write | `test_hit_to_hit_dedup_no_email` PASS |
| HIT → CLEAR | Yes | — | `test_hit_to_clear_emails` PASS |

All 11 matrix entries explicitly covered by passing tests.

---

### Test Counts

| Suite | Tests | Result |
|-------|-------|--------|
| `tests/test_alert_engine.py` | 26 | PASS |
| `tests/test_notifier_stop_alert.py` | 18 | PASS |
| `tests/test_main_alerts.py` | 22 | PASS |
| `tests/test_state_manager.py::TestMigrateV6ToV7` | 7 | PASS |
| `tests/test_dashboard.py::TestRenderAlertBadge` | 11 | PASS |
| `tests/test_web_paper_trades.py::test_edit_resets_last_alert_state` | 4 | PASS |
| `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` | 5 | PASS |
| **Total Phase 20 in-scope** | **93** | **PASS** |
| Broad suite (all tests) | 1586 | PASS |
| Pre-existing failures (unrelated to Phase 20) | 12 | FAIL (nginx/https/ruff — pre-existing) |

---

### Human Verification Required

None — all must-haves are verifiable programmatically for this phase. Email rendering and dashboard badge appearance could optionally be confirmed visually during the next daily run, but all automated checks pass.

---

## Verdict

**PASS.** Phase 20 goal fully achieved. All 30 must-haves verified. ALERT-01..04 complete. Schema bump 6→7 live, two-phase commit wired correctly outside non-reentrant `mutate_state` lock, dedup matrix 11/11 transition pairs tested, hex-boundary preserved, 93 in-scope tests green, 1586 total tests green.

---

_Verified: 2026-04-30_
_Verifier: Claude (gsd-verifier)_
