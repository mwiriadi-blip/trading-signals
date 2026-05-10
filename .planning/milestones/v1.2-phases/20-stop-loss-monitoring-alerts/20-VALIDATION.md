---
phase: 20
slug: stop-loss-monitoring-alerts
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-10
audited: 2026-05-10
---

# Phase 20 — Validation Strategy

> Reconstructed retroactively after phase execution (2026-04-30). All 4 ALERT SC items have automated test coverage; 93 in-scope tests green. Phase 20 VERIFICATION.md confirms PASS with score 30/30.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest tests/test_<task>.py -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Phase-20 subset command** | `.venv/bin/pytest tests/test_alert_engine.py tests/test_notifier_stop_alert.py tests/test_main_alerts.py tests/test_state_manager.py::TestMigrateV6ToV7 tests/test_dashboard.py::TestRenderAlertBadge tests/test_web_paper_trades.py::TestEditPaperTrade::test_edit_resets_last_alert_state tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -q` |
| **Estimated runtime** | ~20 s (Phase-20 subset, 93 tests) |

---

## Sampling Rate

- **After every task commit:** Run task-scoped pytest file (~1–3 s)
- **After every plan wave:** Run full suite (`pytest -q`)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 20 s for Phase-20 subset

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement / Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|------------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 20-T1 | schema-migration-v6-v7 | 1 | `STATE_SCHEMA_VERSION=7`; `_migrate_v6_to_v7` backfills `last_alert_state=None` on paper_trades; idempotent; preserves existing fields | T-20-01-01 | Schema bump does not overwrite existing `last_alert_state` values | unit | `.venv/bin/pytest tests/test_state_manager.py::TestMigrateV6ToV7 tests/test_system_params.py -q` | ✅ | ✅ green |
| 20-T2 | alert-engine-pure-math | 1 | `compute_alert_state` HIT precedence, APPROACHING threshold, CLEAR default, NaN/atr<=0 guards; `compute_atr_distance` NaN on zero ATR | T-20-02-01 | No I/O in pure-math module; forbidden-imports AST gate passes | unit | `.venv/bin/pytest tests/test_alert_engine.py tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -q` | ✅ | ✅ green |
| 20-T3 | notifier-stop-alert-email | 1 | `send_stop_alert_email` success/failure paths; N=0/1/3 subject format; HTML+text parity; XSS escape on string fields; never-crash contract | T-20-03-01 | Every transition field HTML-escaped before email body; inline `style="..."` (not classes) for Gmail compat | unit | `.venv/bin/pytest tests/test_notifier_stop_alert.py -q` | ✅ | ✅ green |
| 20-T4 | main-evaluate-alerts-orchestrator | 1 | `_evaluate_paper_trade_alerts` two-phase commit; transitions vs no_op_writes; send-failure rollback; ATR-NaN safety; call-site outside `mutate_state` closure (D-18 non-reentrancy) | T-20-04-01 | Transitioning rows committed ONLY on `emailed=True`; no_op_writes committed unconditionally; POSIX flock not re-entered | integration | `.venv/bin/pytest tests/test_main_alerts.py -q` | ✅ | ✅ green |
| 20-T5 | dashboard-alert-column | 1 | `_render_alert_badge` every state × has_stop variant; CSS class assertions; Alert column extension; mobile breakpoint; dashboard.py does NOT import alert_engine | T-20-05-01 | No XSS — `html.escape(state)` in badge render | unit | `.venv/bin/pytest tests/test_dashboard.py::TestRenderAlertBadge -q` | ✅ | ✅ green |
| 20-T6 | web-edit-reset | 1 | PATCH `/paper-trade/<id>` resets `last_alert_state=None` on every successful edit regardless of field changed | — | Edit reset is inside `mutate_state` closure (atomic); no race on partial edit | unit (web) | `.venv/bin/pytest tests/test_web_paper_trades.py::TestEditPaperTrade::test_edit_resets_last_alert_state -q` | ✅ | ✅ green |
| 20-T7 | fixtures-and-integration | 1 | `tests/fixtures/state_v7_with_alerts.json` exists with schema_version=7 and 4 paper_trades rows (SPI200/AUDUSD × None/CLEAR/APPROACHING/HIT) | — | Fixture covers both instruments and all four alert states | integration | `.venv/bin/pytest tests/test_main_alerts.py tests/test_notifier_stop_alert.py -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Coverage by Requirement

| Requirement | Description | Test(s) | Status |
|-------------|-------------|---------|--------|
| ALERT-01 | Compute HIT/APPROACHING/CLEAR per open trade with non-null `stop_price` on every daily run | `tests/test_alert_engine.py::TestComputeAlertState` (26 cases); `tests/test_main_alerts.py::TestEvaluatePaperTradeAlerts` | ✅ Covered |
| ALERT-02 | Send `[!stop]`-prefixed email on CLEAR→APPROACHING or *→HIT; batched once per daily run | `tests/test_notifier_stop_alert.py::TestSendStopAlertEmail`; `tests/test_main_alerts.py::test_clear_to_approaching_emails`, `test_initial_none_to_hit_emails` | ✅ Covered |
| ALERT-03 | Dedup via `last_alert_state`; no re-send when same state on consecutive days | `tests/test_main_alerts.py::test_approaching_to_approaching_dedup_no_email`, `test_clear_to_clear_no_email`, `test_hit_to_hit_dedup_no_email` | ✅ Covered |
| ALERT-04 | Dashboard "Alerts" column with CLEAR/APPROACHING/HIT colored badges per open trade | `tests/test_dashboard.py::TestRenderAlertBadge` (11 tests); CSS class assertions and @media breakpoint | ✅ Covered |

---

## Coverage by Threat Reference

| Threat ID | Behavior Verified | Test |
|-----------|-------------------|------|
| T-20-01-01 | Schema migration idempotent; never overwrites existing `last_alert_state` | `TestMigrateV6ToV7::test_idempotent` |
| T-20-02-01 | `alert_engine.py` imports only `math` + `typing`; AST gate blocks forbidden stdlib | `test_forbidden_imports_absent[alert_engine.py]` |
| T-20-03-01 | HTML email fields HTML-escaped; `&lt;script&gt;` in body, not raw `<script>` | `test_html_body_is_html_escaped` |
| T-20-03-02 | Inline `style="..."` in email body (not CSS classes); Gmail mobile compat | `test_html_body_uses_inline_styles_only` |
| T-20-04-01 | `mutate_state` not re-entered; `_evaluate_paper_trade_alerts` called after closure returns | `test_two_phase_commit_ordering_no_deadlock` |
| T-20-04-02 | Send failure rolls back transitioning rows; no_op_writes committed unconditionally | `test_send_failure_rollback`, `test_approaching_to_clear_no_email` |
| T-20-05-01 | Dashboard `_render_alert_badge` calls `html.escape(state)` | `TestRenderAlertBadge` (CSS class substring checks) |

---

## Wave 0 Requirements

Existing infrastructure (pytest 8.x, `tests/` testpath, `.venv/bin/pytest`) covered all phase requirements. No new framework install needed. Per-task test files (`tests/test_alert_engine.py`, `tests/test_notifier_stop_alert.py`, `tests/test_main_alerts.py`) were created during execution and serve as the Nyquist sampling files for Wave 0+.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Operator inbox receives `[!stop]` email with correct HTML table | ALERT-02 | Requires live Resend API key + real OHLCV daily run | Open paper trade with `stop_price` inside 0.5×ATR of yesterday's close; trigger daily run; verify email in `SIGNALS_EMAIL_TO` inbox |
| Dashboard alert badge renders in correct color on production | ALERT-04 | CSS color rendering parity not asserted by unit tests | Visit `/` after daily run; verify CLEAR=green, APPROACHING=amber, HIT=red badges per open trades table |
| Mobile Alert column collapses to pill at <640px | ALERT-04 | `@media` breakpoint behavior requires browser viewport | Open dashboard in mobile browser; verify `.alert-badge { display: block; margin-top: 4px }` activates |

All other phase behaviors have automated verification.

---

## Gaps

None identified. All 4 ALERT SC items are covered by passing tests. The dedup matrix (11 transition pairs) is fully exercised. Hex-boundary (forbidden-imports AST gate), two-phase commit ordering, and send-failure rollback are all tested.

---

## Validation Sign-Off

- [x] All 4 ALERT requirements have automated verify commands
- [x] Sampling continuity: every task has its own test file or test set
- [x] Wave 0 not required — existing infra sufficient
- [x] No watch-mode flags
- [x] Feedback latency < 25 s for full Phase-20 subset
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-10 (retroactive reconstruction; 93 in-scope tests green per 20-VERIFICATION.md 30/30 PASS)

---

## Validation Audit 2026-05-10

| Metric | Count |
|--------|-------|
| Tasks audited | 7 |
| Requirements audited | 4 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Phase-20 tests passing | 93 / 93 |
| Total project tests at ship | 1586 |

Reconstructed from 20-VERIFICATION.md (30/30) and 20-01-SUMMARY.md artifacts; no auditor agent spawned (no gaps to fill).
