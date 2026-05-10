---
phase: 27
slug: code-quality-correctness-sweep-apply-2026-05-07-code-review
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-08
audited: 2026-05-08
---

# Phase 27 — Validation Strategy

> Reconstructed retroactively after phase execution. All 14 tasks have automated test coverage; full suite green.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest tests/test_<task>.py -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Phase-27 subset command** | `.venv/bin/pytest tests/test_decimal_money_math.py tests/test_http_timeouts.py tests/test_secret_redaction.py tests/test_instrument_regex.py tests/test_entry_side_cost.py tests/test_signals_email_to_required.py tests/test_deferred_yfinance_import.py tests/test_version_flag.py tests/test_naive_datetime_fail_closed.py tests/test_migration_contiguity.py tests/test_html_xss_audit.py tests/test_signal_shape_migration.py tests/test_warnings_fifo.py tests/test_run_date_logging.py tests/test_lookahead_bias.py tests/test_crash_email_fallback.py tests/test_notifier_package_seam.py tests/test_main_split_seam.py tests/test_dashboard_split_seam.py -q` |
| **Estimated runtime** | ~47 s (Phase-27 subset, 220 tests); ~3 min (full suite, 2028 tests) |

---

## Sampling Rate

- **After every task commit:** Run task-scoped pytest file (~1–3 s)
- **After every plan wave:** Run full suite (`pytest -q`)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 50 s for Phase-27 subset

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement / Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|------------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 27-01 | decimal-money-math | 1 | Decimal end-to-end PnL/sizing/state v9 | — | No float drift in money arithmetic; quantize-on-save | unit | `.venv/bin/pytest tests/test_decimal_money_math.py tests/test_pnl_engine.py tests/test_sizing_engine.py tests/test_dashboard_decimal_serialization.py -q` | ✅ | ✅ green |
| 27-02 | http-timeout-standardization | 1 | Single `HTTP_TIMEOUT_S` source of truth | T-27-02 | All outbound HTTP uses canonical timeout | unit (AST) | `.venv/bin/pytest tests/test_http_timeouts.py -q` | ✅ | ✅ green |
| 27-03 | api-key-redaction | 1 | `redact_secret` applied to all log/email paths | T-27-03 | API keys never logged in clear | unit | `.venv/bin/pytest tests/test_secret_redaction.py -q` | ✅ | ✅ green |
| 27-04 | instrument-regex-tightening | 1 | `INSTRUMENT_ID_RE` + `is_known_market` two-layer | T-27-04 | No injection via instrument id | unit (AST) | `.venv/bin/pytest tests/test_instrument_regex.py -q` | ✅ | ✅ green |
| 27-05 | magic-cost-helper-and-fallback-email | 1 | `entry_side_cost` helper + email-to fail-closed resolver | T-27-05 | Crash mail never sent to default if unset | unit | `.venv/bin/pytest tests/test_entry_side_cost.py tests/test_signals_email_to_required.py -q` | ✅ | ✅ green |
| 27-06 | deferred-yfinance-and-version-flag | 1 | Lazy yfinance import + `--version` early hook | — | No import-time network/CPU cost | unit | `.venv/bin/pytest tests/test_deferred_yfinance_import.py tests/test_version_flag.py -q` | ✅ | ✅ green |
| 27-07 | naive-datetime-and-migration-contiguity | 1 | Reject naive datetime on `state.append_warning`; contiguous migration chain | T-27-07 | Fail-closed on tz-naive write | unit | `.venv/bin/pytest tests/test_naive_datetime_fail_closed.py tests/test_migration_contiguity.py -q` | ✅ | ✅ green |
| 27-08 | html-escape-audit | 1 | All dynamic dashboard fragments HTML-escaped | T-27-08 | No stored XSS via signal/state fields | unit | `.venv/bin/pytest tests/test_html_xss_audit.py -q` | ✅ | ✅ green |
| 27-09 | signal-shape-unification | 1 | Single dict shape; v9→v10 migration | — | Defensive branches removed safely | unit | `.venv/bin/pytest tests/test_signal_shape_migration.py -q` | ✅ | ✅ green |
| 27-10 | warnings-fifo-rundate-lookahead | 1 | MAX_WARNINGS=50 FIFO; run-date INFO log; look-ahead bias guard | — | No future bars used in backtest | unit | `.venv/bin/pytest tests/test_warnings_fifo.py tests/test_run_date_logging.py tests/test_lookahead_bias.py -q` | ✅ | ✅ green |
| 27-11 | crash-email-fallback | 1 | `last_crash.json` write-never-raise + dashboard banner + secret redaction | T-27-11 | Crash payload never leaks secrets | unit | `.venv/bin/pytest tests/test_crash_email_fallback.py -q` | ✅ | ✅ green |
| 27-12 | notifier-split | 1 | `notifier/` package <500 LOC/file; monkeypatch-target preservation | — | No regression in alert dispatch | unit (seam) | `.venv/bin/pytest tests/test_notifier_package_seam.py tests/test_notifier.py tests/test_notifier_stop_alert.py tests/test_notifier_magic_link.py -q` | ✅ | ✅ green |
| 27-13 | main-split | 1 | `main/` package <550 LOC/file; re-export surface stable | — | Late-bind monkeypatch discipline | unit (seam) | `.venv/bin/pytest tests/test_main_split_seam.py tests/test_main.py tests/test_main_alerts.py -q` | ✅ | ✅ green |
| 27-14 | dashboard-split | 1 | `dashboard_legacy/` package <500 LOC/file; byte-identical render | — | No render drift | unit (seam, byte-equal) | `.venv/bin/pytest tests/test_dashboard_split_seam.py tests/test_dashboard.py tests/test_web_dashboard.py -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure (pytest 8.x, `tests/` testpath, `.venv/bin/pytest`) covered all phase requirements. No new framework install or shared fixture additions needed beyond per-task test files (which were created during execution, not as Wave 0).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual confirmation of `last_crash` banner styling on production dashboard | 27-11 | CSS render parity not asserted by unit tests | Trigger crash via test, view `/` in browser, confirm banner renders red with timestamp + message |
| Live yfinance rate-limit error path | 27-06 | External provider behavior unstable in CI | Manually run `python main.py --once` against live yfinance during a known throttle window |

All other phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All 14 tasks have automated verify commands
- [x] Sampling continuity: every task has its own test file or test set
- [x] Wave 0 not required — existing infra sufficient
- [x] No watch-mode flags
- [x] Feedback latency < 50 s for full Phase-27 subset
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-08 (retroactive reconstruction; full suite green)

---

## Validation Audit 2026-05-08

| Metric | Count |
|--------|-------|
| Tasks audited | 14 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Phase-27 tests passing | 220 / 220 |
| Total project tests | 2028 |

Reconstructed from SUMMARY.md artifacts; no auditor agent spawned (no gaps to fill).
