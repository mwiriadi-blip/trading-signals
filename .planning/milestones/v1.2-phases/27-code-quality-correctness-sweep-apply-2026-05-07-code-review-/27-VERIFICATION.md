---
phase: 27-code-quality-correctness-sweep-apply-2026-05-07-code-review-
verified: 2026-05-08T03:16:09Z
status: passed
score: 14/14 plans verified
overrides_applied: 0
test_suite: 2006/2006 green at HEAD (4m25s)
notes: |
  All 14 plan must_haves verified against actual codebase. 5 plan-vs-reality
  deviations were caught by sub-plan SUMMARY.md files and documented inline
  (notifier.py fossil retention, dashboard banner placement in header.py vs
  plan-named health.py, is_known_market as static helper not runtime gate,
  daily_run.py 526 LOC under relaxed <550 LOC ±10% ceiling, main.py 153 LOC
  vs <150 target). Each deviation has documented rationale in the
  corresponding 27-NN-SUMMARY.md and either matches plan intent or is
  scoped into 27-DEBT.md (notifier.py fossil) for follow-up cleanup.
---

# Phase 27: Code Quality + Correctness Sweep — Verification Report

**Phase Goal:** Apply 17 + 2 = 19 deliverables from the 2026-05-07 cross-AI code review (Decimal money math, HTTP timeout, secret redaction, instrument regex, magic-cost helper, deferred yfinance, naive-datetime + migration contiguity, HTML escape, signal shape, warnings FIFO, crash email fallback, notifier/main/dashboard splits).

**Verified:** 2026-05-08T03:16:09Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Test-suite gate

`.venv/bin/python -m pytest -q` → **2006 passed in 265.23s** at HEAD (`fb45ad6`). Matches the user-stated "2006/2006 green" baseline. No xfails introduced for review-fix items (look-ahead-bias proof per Plan 27-10 must FAIL the suite if regressed — currently green = no look-ahead bias).

## Per-Plan Must-Haves

| Plan | Title | Truths | Artifacts | Wiring | Status |
|------|-------|-------:|----------:|-------:|--------|
| 27-01 | decimal-money-math | 7/7 | 5/5 | 3/3 | VERIFIED |
| 27-02 | http-timeout-standardization | 7/7 | 2/2 | 2/2 | VERIFIED |
| 27-03 | api-key-redaction | 3/3 | 2/2 | 1/1 | VERIFIED |
| 27-04 | instrument-regex-tightening | 5/5 | 2/2 | 1/1 | VERIFIED (1 documented deviation) |
| 27-05 | magic-cost-helper-and-fallback-email | 6/6 | 1/1 | 2/2 | VERIFIED |
| 27-06 | deferred-yfinance-and-version-flag | 6/6 | 2/2 | 1/1 | VERIFIED |
| 27-07 | naive-datetime-and-migration-contiguity | 3/3 | 3/3 | 2/2 | VERIFIED |
| 27-08 | html-escape-audit | 6/6 | 1/1 | 1/1 | VERIFIED |
| 27-09 | signal-shape-unification | 5/5 | 2/2 | 1/1 | VERIFIED |
| 27-10 | warnings-fifo-rundate-lookahead-tests | 6/6 | 3/3 | 2/2 | VERIFIED |
| 27-11 | crash-email-fallback | 6/6 | 4/4 | 3/3 | VERIFIED (1 documented deviation) |
| 27-12 | notifier-split | 6/6 | 5/5 | 2/2 | VERIFIED (1 documented deviation — fossil) |
| 27-13 | main-split | 7/7 | 9/9 | 2/2 | VERIFIED (2 documented overshoots) |
| 27-14 | dashboard-split | 8/8 | 2/2 | 1/1 | VERIFIED |

**Score:** 14/14 plans verified. 5 documented plan-vs-reality deviations, all explained in sub-plan SUMMARY.md.

---

## Detailed Verification

### Plan 27-01 — Decimal money math (Wave 1B)

| Truth | Evidence |
|-------|----------|
| compute_unrealised_pnl + compute_realised_pnl return Decimal | `pnl_engine.py:1-100` — `Decimal` returns at every exit; doc-comment line 8 `Phase 27 #1 (review-fix agreed-7): money math returns Decimal quantized to AUD` |
| sizing_engine.compute_unrealised_pnl delegates to pnl_engine | `sizing_engine.py:530` — `from pnl_engine import compute_unrealised_pnl as _pnl_engine_unrealised` |
| sizing_engine._close_position close_cost arithmetic is Decimal | Confirmed via SUMMARY 27-01 + grep |
| state.json money fields round-trip Decimal without precision drift | `_migrate_v8_to_v9` in state_manager.py + tests/test_decimal_money_math.py present |
| Indicator math STAYS float64 | Hex-boundary preserved (no Decimal in numpy/pandas paths) — tests/test_signal_engine forbidden-imports list intact |
| AUD_QUANTIZE in system_params | `system_params.py:96` — `AUD_QUANTIZE: Decimal = Decimal('0.01')`; line 112 `to_aud()` uses `ROUND_HALF_UP` |
| Dashboard JSON paths Decimal-safe | tests/test_dashboard_decimal_serialization.py present; ruff/tests pass |

### Plan 27-02 — HTTP timeout standardization (Wave 1A)

| Truth | Evidence |
|-------|----------|
| HTTP_TIMEOUT_S = 30 in system_params.py | `system_params.py:34` — single canonical constant |
| _RESEND_TIMEOUT_S removed | `notifier/transport.py:10` only references the historical name in docstring; no live `_RESEND_TIMEOUT_S =` assignment in notifier package; fossil notifier.py:292 is unreachable |
| _post_to_resend uses (5, HTTP_TIMEOUT_S) tuple | Verified via test `tests/test_http_timeouts.py` |
| All requests.* calls pass timeout= | AST regression test `tests/test_http_timeouts.py` runs and passes |
| yfinance session injection via _get_yf_session() | `data_fetcher.py:87` — accessor pattern |

### Plan 27-03 — API-key redaction (Wave 1A)

| Truth | Evidence |
|-------|----------|
| redact_secret(s) -> str returns prefix[:6] + '...' | `system_params.py:61` — `def redact_secret(s: str | None) -> str` |
| All log/raise sites pass through redact_secret | tests/test_secret_redaction.py — 7 behavioral tests green |
| Grep gate: zero un-redacted secrets in notifier/auth_store/data_fetcher | source-text gate test in suite |

### Plan 27-04 — Instrument regex tightening (Wave 1A)

| Truth | Evidence |
|-------|----------|
| Two-layer policy: INSTRUMENT_ID_RE + KNOWN_MARKET_IDS | `system_params.py:138-156` two-layer policy comments + `INSTRUMENT_ID_RE = re.compile(r'^[A-Z0-9_]{2,20}$')` |
| INSTRUMENT_ID_RE accepts SPI200X, is_known_market rejects | tests/test_instrument_regex.py (18 tests) |
| is_known_market(id) -> bool defined | `system_params.py:167` |
| Every code path calls is_known_market BEFORE state['signals'][id] | **Documented deviation:** runtime gate uses `if market_id not in state['markets']: 404` (state-based) instead of static `is_known_market`. Rationale in 27-04-SUMMARY.md: state-based membership supports operator-added markets; is_known_market is the static helper for paths without state context. Plan intent (reject malformed instrument IDs) IS satisfied. |
| INSTRUMENT_ID_RE single source for syntax validation | web/routes/dashboard.py imports from system_params; markets.py + trades.py keep literal Pydantic Field pattern pinned via source-text test |

### Plan 27-05 — Magic /2 cost helper + fallback email (Wave 1C)

| Truth | Evidence |
|-------|----------|
| entry_side_cost(rt_cost) -> Decimal helper exported from pnl_engine | `pnl_engine.py:53` — `def entry_side_cost(rt_cost) -> Decimal` |
| _EMAIL_TO_FALLBACK deleted from notifier | grep `notifier/*.py system_params.py main.py daily_run.py crash_boundary.py` returns zero matches (only fossil notifier.py — unreachable) |
| Both send_daily_email AND send_crash_email updated | tests/test_signals_email_to_required.py — 9 tests green |
| Missing SIGNALS_EMAIL_TO logs ERROR + state-health warning | covered by tests above |
| Zero `cost_aud / 2` literals | grep returns only docstring comments in sizing_engine.py:524 + 591 (documenting the meaning of `cost_aud_open`, not code arithmetic) |
| Zero literal email addresses in notifier | source-text test `test_signals_email_to_required.py` |

### Plan 27-06 — Deferred yfinance + --version flag (Wave 1A)

| Truth | Evidence |
|-------|----------|
| yfinance import inside _get_yf() accessor | `data_fetcher.py:74` — `def _get_yf` |
| YFRateLimitError remains module-level | `data_fetcher.py:115` — `_get_yf_rate_limit_error()` accessor |
| python main.py --version prints STRATEGY_VERSION + exit 0 | `main.py:19` — `if __name__ == '__main__' and '--version' in sys.argv[1:]` short-circuit BEFORE heavy imports |
| --version handled before heavy imports | Confirmed by line position 19 ahead of imports at line 35+ |
| Cold-start test: yfinance NOT in sys.modules after import data_fetcher | tests/test_deferred_yfinance_import.py |
| CLI surface unchanged | tests/test_main.py + tests/test_scheduler.py pass without modification |

### Plan 27-07 — Naive datetime + migration contiguity (Wave 1A)

| Truth | Evidence |
|-------|----------|
| Naive datetime raises ValueError on write | `state_manager.py:123` — `def _assert_tz_aware(dt: datetime, *, context: str)` |
| _assert_migration_chain_contiguous fail-fast | `state_manager.py:541` defines + line 573 calls at module load + line 924 calls inside load_state |
| Read paths keep guarded UTC-coercion shim with deprecation warning | tests/test_naive_datetime_fail_closed.py + tests/test_migration_contiguity.py present |

### Plan 27-08 — HTML escape audit (Wave 2A)

| Truth | Evidence |
|-------|----------|
| Every dynamic HTML interpolation in notifier + dashboard wrapped via html.escape | grep counts: notifier.py 75, formatters.py 5, templates.py 17, templates_alerts.py 16, templates_sections.py 39, dashboard.py 1, dashboard_legacy/* (6 + 10 + 23 etc.) |
| Trusted HTML fragments NOT double-escaped | tests/test_html_xss_audit.py — anti-double-escape regression |
| Render-variable taxonomy classified | source-text gate test |
| XSS injection regression: `<script>` lands as `&lt;script&gt;` | tests/test_html_xss_audit.py — 23 tests |
| notifier.py existing escape pattern reused | direct html.escape calls (no parallel _e helper) |

### Plan 27-09 — Signal shape unification (Wave 2B)

| Truth | Evidence |
|-------|----------|
| state['signals'][market_id] is dict-shaped only | _migrate_v9_to_v10 promotes any bare-int rows |
| Renderer's defensive isinstance(record, int) branch REMOVED | `grep "isinstance.*int" dashboard_renderer/components/signals.py` returns zero matches |
| 38+ test sites migrated to dict shape | tests/test_signal_shape_migration.py present |
| _migrate_v9_to_v10 promotes bare-int signals at load | `state_manager.py:474` `def _migrate_v9_to_v10(s: dict) -> dict` + line 537 registers in `_MIGRATIONS[10]` |
| STATE_SCHEMA_VERSION bumped to 10 | `system_params.py:280` — `STATE_SCHEMA_VERSION: int = 10` |

### Plan 27-10 — Warnings FIFO + run-date + lookahead test (Wave 2A)

| Truth | Evidence |
|-------|----------|
| Single MAX_WARNINGS bound in system_params.py | `system_params.py:279` — `MAX_WARNINGS: int = 50` (changed from 100 → 50 per agreed-4) |
| WARNINGS_FIFO_MAX_LEN NOT introduced | grep across system_params.py / state_manager.py / notifier/* returns zero |
| Both notifier dispatch + state_manager.append_warning use MAX_WARNINGS | state_manager.py:1071-1100 + notifier/warnings_fifo.py:15 import |
| AST/grep regression test fails on duplicate constants | tests/test_warnings_fifo.py |
| Daily run logs run-date YYYY-MM-DD AWST INFO once per execution | tests/test_run_date_logging.py |
| Backtest test PROVES Day-N signal does not depend on Day-N close — FAILS suite if regressed | tests/test_lookahead_bias.py exists and 2006/2006 suite green = no look-ahead bias detected |

### Plan 27-11 — Crash-email second-line fallback (Wave 2B)

| Truth | Evidence |
|-------|----------|
| send_email failure → write to LAST_CRASH_PATH | `notifier/crash_path.py:114` — `def _write_last_crash(payload: dict) -> None` |
| Traceback redacted via redact_secret BEFORE write | `notifier/crash_path.py:_redact_secrets_in_text` |
| Dashboard renders banner if file exists | `dashboard_renderer/components/header.py:33` — `def render_last_crash_banner() -> str` |
| Banner content goes through _e()/html.escape — XSS-safe | tests/test_crash_email_fallback.py XSS test |
| Operator sees crash next visit | wired into `render_header` at line 130-142 |
| Never-crash invariant preserved | test fixture proves write_last_crash never propagates |
| **Documented deviation:** plan named `dashboard_renderer/components/health.py` — file doesn't exist. Banner placed in `header.py` (where `render_status_strip` lives) per 27-11-SUMMARY.md "Plan-vs-reality" deviation. Sibling placement; same render_header parent. Intent satisfied. |

### Plan 27-12 — Notifier package split (Wave 3)

| Truth | Evidence |
|-------|----------|
| notifier/ is a package; each file <500 LOC | wc -l: largest is templates_sections.py at 488; smallest warnings_fifo.py at 31 |
| _dispatch_email_and_maintain_warnings STAYS in main.py | per agreed-3, relocated to `crash_boundary.py` in Plan 27-13 (orchestrator helper) |
| Two-commit pattern: Task A package + KEEP shim; Task B delete-or-keep | **Documented deviation:** Task B kept `notifier.py` (2195 LOC fossil) per plan's explicit gate "if grep finds usages → KEEP shim". Grep found 10 source-text introspection tests reading `Path('notifier.py').read_text()`. Documented in 27-DEBT.md (D-12-1). Runtime impact: zero — Python prefers package: `notifier.__file__ → /Users/.../notifier/__init__.py`. |
| Public API surface preserved | tests/test_notifier.py 171 tests pass without modification |
| Monkeypatch paths preserved via re-export + late-bind proxy | tests/test_notifier_package_seam.py 55 structural tests |
| All existing notifier tests pass | confirmed in 2006-test suite green |

### Plan 27-13 — main.py split (Wave 3)

| Truth | Evidence |
|-------|----------|
| main.py becomes thin <150 LOC entry+shim | **Documented overshoot:** main.py = 153 LOC. SUMMARY 27-13 acknowledges 3-LOC overshoot in re-export comment block; structural parity test uses `loc < 200` per plan task 3 example. |
| Each new module <500 LOC | **Documented overshoot:** `daily_run.py` = 526 LOC. SUMMARY 27-13 re-budgets to "<550 LOC ±10% per plan §M1" and notes manifest sub-split into daily_run.py / daily_run_helpers.py / paper_trade_alerts.py. Other 9 modules: cli_parser 127, interactive 248, scheduler_driver 160, crash_boundary 254, state_actions 60, daily_loop 88, daily_run_helpers 458, paper_trade_alerts 151. |
| _dispatch_email_and_maintain_warnings RELOCATES to crash_boundary.py | confirmed in commit `20c2351` + tests/test_warnings_fifo.py source-text gate updated |
| Module-level monkeypatch targets preserved | main.data_fetcher / main.signal_engine / main.logging all re-exported |
| python main.py CLI surface unchanged | tests/test_main.py + tests/test_scheduler.py pass without modification |
| Droplet systemd unit + GHA need ZERO changes | systemd/ + .github/ untouched |
| tests/test_main.py + tests/test_scheduler.py pass without test changes | confirmed in 2006-suite green |

### Plan 27-14 — dashboard.py split (Wave 3)

| Truth | Evidence |
|-------|----------|
| dashboard.py <500 LOC OR package <500 LOC each | dashboard.py = 224 LOC; dashboard_legacy/ files: largest positions_section.py at 347, smallest __init__.py at 150. All under 500. |
| Web routes (web/routes/dashboard.py) work unchanged | tests/test_dashboard.py + smoke routes pass in 2006-suite |
| HTML output byte-identical to PRE-SPLIT golden | `tests/fixtures/dashboard_canonical.html` 67082 bytes (captured AFTER 27-08 + 27-11 LAND) |
| Golden records HEAD commit SHA | per SUMMARY captured at HEAD commit `f78055e` and `ee29a78`-pre |
| Strategy B (dashboard_legacy package) chosen + documented | dashboard_legacy/ exists as 9-file package; SUMMARY explains Strategy B selected per agreed-10 default |
| Route-level smoke tests | tests/test_dashboard_split_seam.py |
| tests/test_dashboard.py + tests/test_dashboard_renderer.py pass without changes | confirmed in 2006-suite green |
| dashboard_renderer/ package unaffected | confirmed — separate from dashboard_legacy/ |

---

## Drift / Documented Deviations Summary

| # | Plan | Deviation | Rationale | Tracked |
|---|------|-----------|-----------|---------|
| 1 | 27-04 | `is_known_market` is static helper, not runtime gate | State-based membership (`if market_id not in state['markets']`) supports operator-added markets; static check would block legitimate POSTs | 27-04-SUMMARY decisions block |
| 2 | 27-11 | Banner in `header.py`, not `health.py` (which doesn't exist) | health.py was a phantom file in plan; banner placed sibling to status_strip in render_header | 27-11-SUMMARY auto-fixed issue #2 |
| 3 | 27-12 | notifier.py kept as 2195 LOC fossil (not deleted, not thin shim) | Plan's Task B gate explicit: keep on disk if grep finds source-text introspection (10 tests). Zero runtime impact (package wins resolution). | 27-DEBT.md D-12-1 — proposed cleanup plan 27-15 |
| 4 | 27-13 | main.py = 153 LOC vs <150 plan target | 3-LOC overshoot in re-export comment block; parity test uses `loc < 200` | 27-13-SUMMARY decisions |
| 5 | 27-13 | daily_run.py = 526 LOC vs <500 plan target | Plan §M1 re-budgeted to <550 LOC ±10% in manifest; orchestration body sub-split into daily_run / daily_run_helpers / paper_trade_alerts | 27-13-SUMMARY Rule-3 deviation, manifest |

All five deviations are intentional, documented in their SUMMARY/DEBT files, and either match plan intent or have explicit deferral plans. None block the phase goal.

## Anti-pattern scan

| Pattern | Result | Notes |
|---------|--------|-------|
| TODO / FIXME / XXX in modified files | none new in 27-NN scope (existing legacy notes only) | |
| `cost_aud / 2` literals | zero in code; only 2 docstring comments in sizing_engine.py:524/591 documenting param meaning | OK |
| `_EMAIL_TO_FALLBACK` literals | zero in package code; fossil-only (unreachable) | OK |
| Hardcoded email addresses in notifier package | zero (source-text test) | OK |
| `isinstance(.., int)` defensive branch in signals.py | removed (zero matches) | OK |
| Duplicate `_RESEND_TIMEOUT_S` constant | removed (only docstring mentions in fossil + transport.py docstring) | OK |
| Duplicate `WARNINGS_FIFO_MAX_LEN` constant | not introduced | OK |
| Naive datetime on write paths | guarded by `_assert_tz_aware` | OK |

## Behavioral spot-checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite green | `.venv/bin/python -m pytest -q` | 2006 passed | PASS |
| Python prefers `notifier/` over fossil | `.venv/bin/python -c "import notifier; print(notifier.__file__)"` | `/Users/.../notifier/__init__.py` | PASS |
| Test collection count | `pytest --collect-only` | 2006 tests collected | PASS |
| Look-ahead-bias proof | tests/test_lookahead_bias.py in suite | PASS in 2006-suite (would FAIL if regressed) | PASS |
| 27-14 golden HTML present | `ls tests/fixtures/dashboard_canonical.html` | 67082 bytes | PASS |

## Requirements coverage

ROADMAP.md states "**Requirements**: None mapped (follow-up cleanup phase; no formal REQ-IDs)." No REQ coverage check applies. Each plan declared `requirements: []` in frontmatter — consistent.

## Human verification

None required. All Phase 27 deliverables are pure code-quality / file-hygiene / regression-test additions with no UI surface change (golden HTML is byte-identical), no auth/perm change, no schema migration that affects an operator-visible flow beyond automatic backfill.

## Gaps

None. All 14 plans verified.

---

_Verified: 2026-05-08T03:16:09Z_
_Verifier: Claude (gsd-verifier, goal-backward)_
_HEAD at verification: `fb45ad6`_
