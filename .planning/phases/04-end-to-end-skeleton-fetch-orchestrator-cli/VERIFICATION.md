---
phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
verified: 2026-04-22T05:40:00+08:00
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: 'Run `.venv/bin/python main.py --test` against live yfinance'
    expected: 'Full D-14 per-instrument log block for ^AXJO and AUDUSD=X plus [Sched] footer with state_saved=false (--test); rc=0; state.json mtime unchanged; no traceback'
    why_human: 'Exercises the live yfinance HTTPS path end-to-end — tests only use recorded fixtures via monkeypatch. This is the last gap between "pytest green on fixtures" and "the operator actually gets a real run". Phase 4 acceptance always includes at least one real-network smoke check per 04-04 SUMMARY §Authentication Gates ("manual smoke-test ... noted in the plan as optional").'
  - test: 'Run `.venv/bin/python main.py --once` once against live yfinance after a prior successful --test'
    expected: 'Same D-14 log block; state.json mtime changes exactly once; `state.json` contains post-run account / positions / signals / equity_history / last_run entries and signal_as_of reflects the market-local last bar date'
    why_human: 'The structural difference between --test and --once is "does save_state fire?" — pytest covers it via mtime assertions on fixtures, but only a live run produces the actual on-disk state.json the operator will consume in Phase 5/6/7. Verifies the single-atomic-save-at-end-of-run contract (D-11 step 9).'
  - test: 'Inspect the [State] position / [State] trade closed / [State] SPI200 WARNING: size=0 skipping trade lines when a trade path triggers'
    expected: 'Log lines render with the exact D-14 prefixes + numeric formatting (e.g. `trail_stop=8120.1`, `unrealised=+$850`, `WARNING: size=0 skipping trade`) as specified in 04-RESEARCH §Example 4'
    why_human: 'D-14 numeric formatting (%+.0f for unrealised, %.1f for trail_stop, `$` sign conventions) is checked structurally by caplog but human eyeball is better at catching subtle layout issues before Phase 5 dashboard reads the same numbers.'
---

# Phase 4: End-to-End Skeleton — Fetch + Orchestrator + CLI — Verification Report

**Phase Goal:** Wire the signal engine and state manager together behind a real yfinance fetch, with CLI flags, structured logs, and a top-level error boundary — `python main.py --once` reads Yahoo, computes signals, updates state, and prints a readable console summary. No email, no dashboard yet.
**Verified:** 2026-04-22T05:40:00+08:00
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria, amended 2026-04-22 per C-1)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `python main.py --once` fetches 400 days of OHLCV for `^AXJO` and `AUDUSD=X`, retries up to 3× with 10s backoff on failure, and prints a structured per-instrument log block plus a run summary | VERIFIED | `data_fetcher.fetch_ohlcv(days=400, retries=3, backoff_s=10.0)` with retry loop in `data_fetcher.py:93-132`; tests `test_happy_path_axjo_returns_400_bars`, `test_happy_path_audusd_returns_400_bars`, `test_retry_on_rate_limit_then_success`, `test_retry_on_timeout_then_success`, `test_retry_on_connection_error_then_success`, `test_empty_frame_exhausts_retries_then_raises_data_fetch_error`, `test_once_flag_runs_single_check`, `test_log_format_matches_d14_contract` all pass. D-14 per-instrument block emitted by `_format_per_instrument_log_block` (`main.py:217-282`); run-summary footer by `_format_run_summary_footer` (`main.py:285-310`). |
| 2 | A short/empty frame (len < 300) hard-fails the run — no state written, error logged, exit non-zero; stale last-bar is logged as a warning but not fatal | VERIFIED | DATA-04 gate: `main.py:401-404` `raise ShortFrameError(f'{yf_symbol}: only {len(df)} bars, need >= {_MIN_BARS_REQUIRED}')` with `_MIN_BARS_REQUIRED=300`; caught by typed-exception boundary `main.py:687-689` → exit 2. Test `test_short_frame_raises_and_no_state_written` asserts `pytest.raises(ShortFrameError, match='need >= 300')` AND state.json mtime unchanged. DATA-05 stale path: `main.py:416-428` logs `[Fetch] WARN` and appends `('fetch', <message>)` to `pending_warnings`; flush loop at `main.py:537-538` persists via `state_manager.append_warning`. Test `test_stale_bar_appends_warning` asserts rc=0, state.warnings contains `'6d old'` and `'(threshold=3d)'` strings, and `[Fetch] WARN` at WARNING level in caplog. |
| 3 | `signal_as_of` (last data-bar date) and `run_date` (Perth clock-now) are both logged on every run and never substituted for each other | VERIFIED | `signal_as_of` derived from `df.index[-1].strftime('%Y-%m-%d')` (no tz conversion per D-13) in `main.py:407`. `run_date = _compute_run_date()` reads `datetime.now(tz=AWST)` in `main.py:131-139`. Both emitted in opening `[Sched] Run <run_date> mode=...` line (`main.py:374-376`) and in every `[Signal] <sym> signal_as_of=<date>` line (`main.py:246-250`). Test `test_signal_as_of_and_run_date_logged_separately` (frozen 2026-04-21 09:00:03+08:00) asserts BOTH `signal_as_of=2026-04-19`, `signal_as_of=2026-04-20`, AND `Run 2026-04-21 09:00:03 AWST` appear in caplog.text. |
| 4 | `python main.py --test` produces the full computed summary and leaves `state.json` mtime unchanged (structurally separated compute vs persist) | VERIFIED | Step 8 structural guard `main.py:545-554`: `if args.test: ... return 0` BEFORE the single `state_manager.save_state(state)` at step 9 (`main.py:557`). Function-scoped AST gate confirms exactly ONE save_state call inside `run_daily_check`. Test `test_test_flag_leaves_state_json_mtime_unchanged` records `st_mtime_ns` before and after `main.main(['--test'])`, asserts equality. |
| 5 | `python main.py --reset` reinitialises state after confirmation; `python main.py --once` exits cleanly for GHA use; default `python main.py` runs once and exits in Phase 4 (schedule-loop wiring lands in Phase 7 per SCHED-01/02; `--force-email` and `--test`-email are stubbed in Phase 4 and wired in Phase 6 per NOTF-01) | VERIFIED | `_handle_reset` (`main.py:579-610`): RESET_CONFIRM env bypass + EOFError-safe `input()` prompt → `state_manager.reset_state()` + `save_state()` on confirm, exit 1 on cancel. `_force_email_stub` (`main.py:613-632`) emits `[Email] --force-email received; notifier wiring arrives in Phase 6` with C-8 Phase 6 dispatch-shape note in docstring. `main()` dispatch ladder (`main.py:667-694`): `--reset` → `_handle_reset()`; `--force-email + --test` → `run_daily_check(args)` then `_force_email_stub()`; `--force-email` alone → stub only; default/`--once`/`--test` alone → `run_daily_check`. D-07 log line `[Sched] One-shot mode (scheduler wiring lands in Phase 7)` emitted at `main.py:377`. Tests `test_reset_with_confirmation_writes_fresh_state`, `test_reset_without_confirmation_does_not_write`, `test_force_email_logs_stub_and_exits_zero`, `test_once_flag_runs_single_check`, `test_default_mode_runs_once_and_logs_schedule_stub` all pass. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `main.py` | Orchestrator with `run_daily_check`, `_compute_run_date`, `_closed_trade_to_record`, `_handle_reset`, `_force_email_stub`, `main`, `_build_parser`, `_validate_flag_combo`, D-14 log formatters; imports allowed hexes only | VERIFIED | 699 lines; all 12+ functions present and implemented; zero `NotImplementedError` / `TODO` / `FIXME` / `HACK`; imports `data_fetcher`, `signal_engine`, `sizing_engine`, `state_manager`, `system_params` + stdlib only; no `yfinance`/`requests`/`pandas`/`numpy` (AST gate `test_main_no_forbidden_imports` passes). |
| `data_fetcher.py` | yfinance I/O hex with `fetch_ohlcv`, `DataFetchError`, `ShortFrameError`; retry loop + narrow-catch + empty-frame guard + C-6 required-column gate | VERIFIED | 133 lines; retry loop `data_fetcher.py:93-132`; narrow-catch tuple `(*_RETRY_EXCEPTIONS, ValueError)` at `:121`; C-6 `_REQUIRED_COLUMNS` frozenset gate raises domain-specific `DataFetchError` at `:114-119` (non-retry-eligible schema drift); defensive column slice at `:120`; AST gate `test_data_fetcher_no_forbidden_imports` passes against `FORBIDDEN_MODULES_DATA_FETCHER = {signal_engine, sizing_engine, state_manager, notifier, dashboard, main, numpy, schedule, dotenv, pytz}`. |
| `tests/test_main.py` | `TestCLI` (5 methods) + `TestOrchestrator` (7 methods — 6 Wave 2 + 1 Wave 3 stale + 1 Wave 3 ERR-01 makes 8, actual count 8 by audit) + `TestLoggerConfig` (1 method); covers CLI-01..05, DATA-04..06, ERR-01, ERR-06, D-08, D-12, AC-1, Pitfall 4 | VERIFIED | Test suite shows 15 test methods: 5 in `TestCLI` (once / default / --test mtime / reset-confirm / reset-cancel / force-email), 8 in `TestOrchestrator` (short-frame, signal_as_of vs run_date, D-14 log, closed_trade_to_record D-12/Pitfall 8, D-08 int/dict + G-2, AC-1 reversal, stale-bar DATA-05, fetch-failure ERR-01), 1 in `TestLoggerConfig` (Pitfall 4 dummy-handler proof-by-consequence). All pass. C-4 caplog strategy (`monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)`) applied consistently across 10 caplog-asserting tests. |
| `tests/test_data_fetcher.py` | `TestFetch` (6 methods covering DATA-01/02/03 + retry variants + empty-frame exhaust) + `TestColumnShape` (2 methods: Pitfall 1 strip + C-6 missing-columns) | VERIFIED | 277 lines; `TestFetch` has 6 methods, `TestColumnShape` has 2 methods — 8 offline tests total using `_FakeTicker` factory pattern + `monkeypatch.setattr('data_fetcher.yf.Ticker', ...)`. All pass. |
| `tests/test_signal_engine.py` | Extended AST blocklist covering Phase 4 new modules: `FORBIDDEN_MODULES_DATA_FETCHER`, `FORBIDDEN_MODULES_MAIN` (C-5 expanded to {numpy, yfinance, requests, pandas}), new parametrized methods `test_data_fetcher_no_forbidden_imports` + `test_main_no_forbidden_imports`, 2-space-indent guard extended to Phase 4 paths | VERIFIED | `FORBIDDEN_MODULES_DATA_FETCHER` at `tests/test_signal_engine.py:517-526` (11 entries incl. sibling hexes + numpy + schedule + dotenv + pytz); `FORBIDDEN_MODULES_MAIN` at `:536-541` (4 entries: numpy, yfinance, requests, pandas — C-5 verified); parametrized test methods at `:780-798` and `:800-816`. Both pass. |
| `tests/fixtures/fetch/axjo_400d.json` | Committed recorded yfinance fixture, >= 400 bars, orient='split' round-trip | VERIFIED | 55,152 bytes; 599 bars per 04-01 SUMMARY; `pd.read_json(path, orient='split')` round-trips losslessly in `_load_recorded_fixture`; last bar 2026-04-19 confirmed by DATA-06 test assertion. |
| `tests/fixtures/fetch/audusd_400d.json` | Committed recorded yfinance fixture, >= 400 bars, orient='split' round-trip | VERIFIED | 49,207 bytes; 595 bars per 04-01 SUMMARY; last bar 2026-04-20 confirmed by DATA-06 test assertion. |
| `tests/regenerate_fetch_fixtures.py` | Offline-only regenerator, C-9 routed through `data_fetcher.fetch_ohlcv` | VERIFIED | Uses `from data_fetcher import fetch_ohlcv`; `days=600` over-fetch documented; raw `yf.Ticker` removed per 04-02 SUMMARY. |
| `requirements.txt` | `pytest-freezer==0.4.9` pinned in alphabetical order | VERIFIED | Line 4: `pytest-freezer==0.4.9`. Plugin registration confirmed via `.venv/bin/pytest -VV` (C-10 revision). |
| `.planning/REQUIREMENTS.md` | Amended 2026-04-22 per C-1 — CLI-01, CLI-03, CLI-05 Phase 4 ↔ Phase 6/7 split wording | VERIFIED | Line 4 `**Amended:** 2026-04-22 (CLI-01, CLI-03, CLI-05 Phase 4 ↔ Phase 6/7 split — per Phase 4 cross-AI review 04-REVIEWS.md C-1)`; CLI-01/03/05 bodies at lines 135/137/139 describe the split explicitly. Traceability table rows 262-266 tag multi-phase coverage. |
| `.planning/ROADMAP.md` | Amended 2026-04-22 per C-1 — Phase 4 SC-5 wording reflects Phase 4/6/7 split | VERIFIED | Line 4 `**Amended:** 2026-04-22 (Phase 4 SC-5 wording — per Phase 4 cross-AI review 04-REVIEWS.md C-1)`; SC-5 at line 87 includes the `schedule-loop wiring lands in Phase 7 per SCHED-01/02; --force-email and --test-email are stubbed in Phase 4 and wired in Phase 6 per NOTF-01` clause. |
| `system_params.py` | No new Phase 4 constants needed | VERIFIED | Phase 4 adds no new system_params constants — reuses `SPI_MULT`, `SPI_COST_AUD`, `AUDUSD_NOTIONAL`, `AUDUSD_COST_AUD` from Phase 2, plus `INITIAL_ACCOUNT` from Phase 3. Phase 4-specific constants (`SYMBOL_MAP`, `_SYMBOL_CONTRACT_SPECS`, `_MIN_BARS_REQUIRED`, `_STALE_THRESHOLD_DAYS`) live in `main.py` at module scope. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|------|------|------|---------|
| `main.run_daily_check` | `data_fetcher.fetch_ohlcv` | `df = data_fetcher.fetch_ohlcv(yf_symbol, days=400, retries=3, backoff_s=10.0)` (`main.py:395-397`) | WIRED | Explicit call with all 4 parameters matching DATA-01/02/03. Fetch elapsed time captured via `time.perf_counter()` for D-14 log. |
| `main.run_daily_check` | `signal_engine.compute_indicators` / `get_latest_indicators` / `get_signal` | Lines `main.py:432-434` | WIRED | All three Phase 1 public API functions invoked in sequence; scalars persisted to `state['signals'][state_key]['last_scalars']` (G-2) at line 514-519. |
| `main.run_daily_check` | `sizing_engine.step` | Line `main.py:455-464` with 8-arg signature (position, bar, indicators, old_signal, new_signal, account, multiplier, cost_aud_open) | WIRED | Phase 2 D-17 expanded signature honoured; result unpacked (`position_after`, `closed_trade`, `unrealised_pnl`, `warnings`) in log block + state mutation + record_trade. |
| `main.run_daily_check` | `state_manager.load_state` / `save_state` / `record_trade` / `update_equity_history` / `append_warning` | Lines `main.py:380, 504, 534, 538, 557` | WIRED | All 5 Phase 3 public API entry points invoked at correct D-11 step positions. `save_state` is the single commit point at step 9 (AST gate verified: exactly 1 call inside `run_daily_check`). |
| `main._format_per_instrument_log_block` | `sizing_engine.get_trailing_stop` | Line `main.py:252-254` | WIRED | Phase 2 trailing-stop computed inline for the [State] position log line. |
| `main._force_email_stub` | `notifier.send_daily_email` | C-8 docstring note at `main.py:615-629` documenting Phase 6 dispatch shape | PARTIAL (BY DESIGN — Phase 6 scope) | Stub emits log line + returns 0 per D-06. Phase 6 replaces body with `rc = run_daily_check(args); if rc == 0: notifier.send_daily_email(...); return rc`. Phase 4 scope boundary — not a gap. |
| `main._handle_reset` | `state_manager.reset_state` / `save_state` | `main.py:607-608` | WIRED | CLI-02 confirmation path ends with fresh state persisted. Second `save_state` site is valid per C-7 (AST gate scoped to `run_daily_check` only). |
| `main()` typed-exception boundary | `DataFetchError`, `ShortFrameError` → exit 2; `Exception` → exit 1 | `main.py:687-694` | WIRED | Test `test_fetch_failure_exits_nonzero_no_save_state` asserts `rc == 2` for DataFetchError and `state.json` mtime unchanged; ERR-04 crash-email is explicitly Phase 8 scope. |
| `run_daily_check` AC-1 reversal ordering | `record_trade` called BEFORE `state['positions'][state_key] = result.position_after` | `main.py:492-510` | WIRED | AST check confirms `record_trade` at line 188 of `run_daily_check`'s function-scoped AST and position assignment at line 194 — `ordering ok: True`. Test `test_reversal_long_to_short_preserves_new_position` asserts post-run `state['positions']['SPI200'] is not None` AND `direction == 'SHORT'` AND `n_contracts == 3` AND trade_log[0].entry_date == '2026-04-10' (pre-close capture). |

### Data-Flow Trace (Level 4)

Phase 4 is a fetch/orchestrator/CLI phase — the dynamic-data-render model applies to `run_daily_check` itself as the adapter between live yfinance output and persisted state. Tracing:

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `main.run_daily_check` | `df` (per-symbol OHLCV DataFrame) | `data_fetcher.fetch_ohlcv(yf_symbol, days=400, retries=3, backoff_s=10.0)` | Yes — real yfinance HTTPS path; fixture-replayed in tests | FLOWING |
| `main.run_daily_check` | `scalars` (8-key indicator dict) | `signal_engine.get_latest_indicators(df_with_indicators)` | Yes — pure-math output fed from real df | FLOWING |
| `main.run_daily_check` | `new_signal` (int) | `signal_engine.get_signal(df_with_indicators)` | Yes — 2-of-3 momentum vote with ADX gate from Phase 1 | FLOWING |
| `main.run_daily_check` | `result.closed_trade` / `result.position_after` | `sizing_engine.step(...)` | Yes — Phase 2 9-cell transition matrix, real scalars, real bar | FLOWING |
| `state['signals'][state_key]` persisted | 4-key dict incl. `last_scalars` | In-loop assignment line 514-519 | Yes — G-2 revision lands real scalars for Phase 5/6 consumption | FLOWING |
| `state['equity_history']` | sum(account + unrealised across positions) | `sizing_engine.compute_unrealised_pnl` per-symbol aggregation at lines 521-531 + `state_manager.update_equity_history(state, run_date_iso, equity)` at line 534 | Yes — per-symbol multipliers looked up afresh from `_SYMBOL_CONTRACT_SPECS`; no stale last-iteration reuse | FLOWING |
| `state['warnings']` (stale-bar DATA-05) | FIFO-bounded warning list | `pending_warnings.append((...))` at line 424-428 + flush loop at 537-538 | Yes — test seeds a 6d-stale df and asserts the warning lands in post-run state['warnings'] with the exact `'6d old'` + `'(threshold=3d)'` substrings | FLOWING |

No hollow wiring detected. All data sinks (state.json fields) trace back to real data sources with production code paths.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full pytest suite green | `.venv/bin/pytest tests/ -q` | `319 passed in 1.60s` | PASS |
| Ruff clean across whole repo | `.venv/bin/ruff check .` | `All checks passed!` | PASS |
| No stubs / markers in Phase 4 files | `grep NotImplementedError TODO FIXME HACK main.py data_fetcher.py tests/test_main.py tests/test_data_fetcher.py` | 0 matches in all 4 files | PASS |
| `--force-email` smoke (no network) | `.venv/bin/python -c "import main; main.main(['--force-email'])"` | `[Email] --force-email received; notifier wiring arrives in Phase 6` + rc=0 | PASS |
| D-05 flag-exclusivity via argparse | `.venv/bin/python -c "import main; main.main(['--reset','--test'])"` | `SystemExit code: 2` with `error: --reset cannot be combined with other flags` | PASS |
| CLI --help renders | `.venv/bin/python main.py --help` | Full help text with all 4 flags + Phase 4/6/7 deferred-wiring notes | PASS |
| AC-1 mutation ordering (AST) | `.venv/bin/python ... ast.walk(run_daily_check)` | `record_trade_line=188 < position_assign_line=194` | PASS |
| C-7 save_state single-call in run_daily_check | `.venv/bin/python ... ast.walk(run_daily_check)` | `save_state count = 1` | PASS |
| basicConfig single-call site | `.venv/bin/python ... ast.walk(main_module)` | `basicConfig call count = 1` | PASS |
| Pitfall 8 — no realised_pnl in _closed_trade_to_record | `.venv/bin/python ... ast.unparse(_closed_trade_to_record)` | `'realised_pnl' in ...: False` | PASS |
| Phase-specific test subset green | `.venv/bin/pytest tests/test_main.py tests/test_data_fetcher.py tests/test_signal_engine.py::TestDeterminism -q` | `65 passed in 0.87s` | PASS |
| Live yfinance `python main.py --test` | Would require network; skipped | N/A | SKIP (routed to human verification) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-01 | 04-02 | Fetch 400 days of ^AXJO OHLCV via yfinance | SATISFIED | `test_happy_path_axjo_returns_400_bars` asserts >= 400 bars + column order + DatetimeIndex preserved; retry loop active. |
| DATA-02 | 04-02 | Fetch 400 days of AUDUSD=X OHLCV via yfinance | SATISFIED | `test_happy_path_audusd_returns_400_bars` mirrors DATA-01 for AUDUSD. |
| DATA-03 | 04-02 | Fetch retries up to 3 times with 10s backoff | SATISFIED | Retry loop `for attempt in range(1, retries + 1)` with `time.sleep(backoff_s)` between attempts. Tests `test_retry_on_rate_limit_then_success`, `test_retry_on_timeout_then_success`, `test_retry_on_connection_error_then_success`, `test_empty_frame_exhausts_retries_then_raises_data_fetch_error` cover all 4 retry-eligible exception types. Default `backoff_s=10.0`. |
| DATA-04 | 04-03 | Short frame (len < 300) raises hard fail — no state written | SATISFIED | `test_short_frame_raises_and_no_state_written` asserts `ShortFrameError` raised with `'need >= 300'` match AND `state.json` mtime unchanged. |
| DATA-05 | 04-04 | Stale last bar flagged as warning | SATISFIED | `test_stale_bar_appends_warning` (frozen 2026-04-21 + hand-built 6d-stale df) asserts warning lands in `state['warnings']` with `'6d old'` + `'(threshold=3d)'` substrings AND `[Fetch] WARN` at WARNING level in caplog. D-09 threshold=3 days enforced via `_STALE_THRESHOLD_DAYS = 3` module constant. |
| DATA-06 | 04-03 | `signal_as_of` logged separately from `run_date` | SATISFIED | `test_signal_as_of_and_run_date_logged_separately` (frozen 2026-04-21 09:00:03+08:00) asserts BOTH `signal_as_of=2026-04-19`, `signal_as_of=2026-04-20`, AND `Run 2026-04-21 09:00:03 AWST` appear in caplog.text. D-13 no-tz-conversion contract honoured. |
| CLI-01 | 04-04 | `--test` runs full check and does NOT mutate state.json | SATISFIED (Phase 4 scope — structural read-only) | `test_test_flag_leaves_state_json_mtime_unchanged` asserts `st_mtime_ns` before == after. REQUIREMENTS.md line 135 acknowledges Phase 6 will add the `[TEST]`-prefixed email send. |
| CLI-02 | 04-04 | `--reset` reinitialises state.json after confirmation | SATISFIED | Two tests: `test_reset_with_confirmation_writes_fresh_state` (RESET_CONFIRM=YES bypass) + `test_reset_without_confirmation_does_not_write` (input!='YES' cancels, returns exit 1, mtime unchanged). EOFError-safe `input()`. |
| CLI-03 | 04-04 | `--force-email` sends today's email | SATISFIED (Phase 4 scope — stub + --test combo) | `test_force_email_logs_stub_and_exits_zero` asserts the exact Phase 4 stub log line. C-8 docstring records Phase 6 dispatch shape. REQUIREMENTS.md line 137 acknowledges Phase 6 wires the notifier. |
| CLI-04 | 04-03 | `--once` runs one daily check for GHA | SATISFIED | `test_once_flag_runs_single_check` asserts rc=0 + exactly 2 fetch calls (one per symbol) + D-07 one-shot log line. |
| CLI-05 | 04-03 | Default invocation runs and enters schedule loop | SATISFIED (Phase 4 scope — default == one-shot) | `test_default_mode_runs_once_and_logs_schedule_stub` proves `main.main([])` == `main.main(['--once'])` in Phase 4. REQUIREMENTS.md line 139 + ROADMAP.md line 87 acknowledge Phase 7 flips default to scheduler loop. |
| ERR-01 | 04-04 | yfinance failure after 3 retries exits gracefully | SATISFIED (Phase 4 scope — exits non-zero without traceback noise; email send is Phase 8 scope via ERR-04 crash-email) | `test_fetch_failure_exits_nonzero_no_save_state` asserts `rc == 2` for DataFetchError AND state.json mtime unchanged AND `[Fetch] ERROR:` log line. Phase 8 will add the crash-email layer. |
| ERR-06 | 04-03 | Console logs use a structured format readable in Replit/GHA | SATISFIED | `test_log_format_matches_d14_contract` asserts all D-14 prefixes `[Fetch]`, `[Signal]`, `[State]`, `[Sched]` + `last_bar=2026-04-19`, `ADX=`, `rvol=`, `AWST done in` substrings all present in caplog.text. |

**No ORPHANED requirements:** REQUIREMENTS.md Traceability table rows 195-200 (DATA-01..06), 262-266 (CLI-01..05), 267 + 272 (ERR-01 + ERR-06) all map to Phase 4, and all are claimed by at least one of the 4 plans' `requirements:` frontmatter fields.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| n/a | n/a | n/a | n/a | No anti-patterns detected |

Specifically:
- **`NotImplementedError` / `TODO` / `FIXME` / `HACK`:** 0 matches across `main.py`, `data_fetcher.py`, `tests/test_main.py`, `tests/test_data_fetcher.py`.
- **Placeholder UI or "coming soon" strings:** 0 matches.
- **Empty/stub returns:** `_force_email_stub` returns 0 intentionally by Phase 4 design (C-8 Phase 6 note in docstring) — this is a scope boundary, not a stub regression. REQUIREMENTS.md CLI-03 wording explicitly permits this for Phase 4.
- **Hardcoded empty collections in rendered paths:** `pending_warnings = []` at `main.py:384` is an initial-state variable that the DATA-05 stale-bar path populates (verified by `test_stale_bar_appends_warning`) — not a stub.
- **Console.log-only handlers:** `_force_email_stub` is a deliberate log-and-exit stub per CLI-03 Phase 4 scope (REQUIREMENTS.md line 137 + ROADMAP.md Phase 6 SC-6 acknowledge Phase 6 wires the actual dispatch). Classified as INFO (intentional, scope-boundary) — not a warning or blocker.

### Human Verification Required

Three items need human testing — all concern the live-yfinance / live-filesystem path that pytest cannot exercise without network access or real clock mutation:

#### 1. Live yfinance `--test` smoke

**Test:** Run `.venv/bin/python main.py --test` at the project root against live yfinance.
**Expected:** Full D-14 per-instrument log block for `^AXJO` and `AUDUSD=X` to stderr, plus the `[Sched] Run <AWST-now> AWST done in <X.Xs> — instruments=2, trades_recorded=0, warnings=0, state_saved=false (--test)` footer; rc=0; `state.json` mtime unchanged relative to a pre-run snapshot; no traceback noise.
**Why human:** Tests only exercise the recorded-fixture path via `monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', ...)`. The live yfinance HTTPS retry loop has never been exercised in CI. This is the last gap between "pytest green on fixtures" and "the operator actually gets a real run". 04-04 SUMMARY §Authentication Gates explicitly notes this as an optional manual smoke.

#### 2. Live yfinance `--once` smoke with post-run state inspection

**Test:** Run `.venv/bin/python main.py --once` after the --test smoke above completes cleanly.
**Expected:** Same D-14 log block; `state.json` mtime changes exactly once (atomic single-save contract); post-run `state.json` contains valid `account` / `positions` / `signals` / `equity_history` / `last_run` entries; each `state.signals.{SPI200,AUDUSD}` is a dict with keys `{signal, signal_as_of, as_of_run, last_scalars}` and `last_scalars` is a real scalars dict with `adx` / `mom1` / `mom3` / `mom12` / `rvol` keys.
**Why human:** The structural difference between `--test` and `--once` is "does save_state fire at step 9?" — pytest covers it via mtime assertions on fixture paths, but only a live run produces the actual on-disk `state.json` that Phase 5 (dashboard), Phase 6 (email), and Phase 7 (GHA commit-back) will consume. D-08 + G-2 persistence shape needs human eyeballs on real JSON.

#### 3. D-14 log formatting visual check

**Test:** Review the stderr output from runs 1 and 2 above; confirm each per-instrument block looks like 04-RESEARCH §Example 4.
**Expected:** Exact shape (verbatim for at least the `[Fetch] <sym> ok: N bars, last_bar=YYYY-MM-DD, fetched_in=X.Xs` line; numeric formatting for unrealised P&L as `+$NNN` or `-$NNN`; trail_stop rendered to 1 dp; closed-trade line rendered only on trade-close bars; no spurious blank lines between prefixes).
**Why human:** D-14 numeric formatting (`%+.0f` for unrealised, `%.1f` for trail_stop, `%.2f` for P&L, conditional `no position` / `no trades closed this run` lines) is checked in pytest via caplog substring assertions, but subtle layout issues (extra blank lines, off-by-one whitespace, missing separators between instruments) are much easier to catch by eye before Phase 5 dashboard tries to pattern-match them for structured extraction.

### Gaps Summary

**No blocking gaps.** All 5 ROADMAP.md Phase 4 Success Criteria verified via automated tests; all 13 in-scope requirements (DATA-01..06, CLI-01..05, ERR-01, ERR-06) have named passing pytest nodes; all 4 cross-AI review revisions landed (AC-1 ordering, C-1 upstream-doc amendments, C-5 FORBIDDEN_MODULES_MAIN, C-6 missing-columns, C-7 function-scoped AST save_state gate, C-8 Phase 6 docstring, C-9 regenerator switchover, C-10 pytest CLI plugin check, G-2 last_scalars, G-3 import time, G-4 warnings emission); zero anti-patterns; 319 tests pass; ruff clean.

The only outstanding work is human verification of the live-yfinance path (3 items above) — automated checks alone cannot confirm that real-world HTTPS + filesystem interactions behave correctly end-to-end. This is a standard "automation proves structure, human proves behaviour in production-like environment" gate and is NOT a closure-plan input.

Scope boundaries intentionally left for later phases (not gaps):
- `--force-email` Resend dispatch → Phase 6 (NOTF-01) — C-8 docstring notes Phase 6 shape.
- `--test`-email `[TEST]`-prefixed Resend send → Phase 6 (NOTF-01) — CLI-01 split across Phase 4/6.
- Scheduler loop default-mode behaviour → Phase 7 (SCHED-01/02) — CLI-05 split across Phase 4/7.
- Stale-state email banner, ERR-04 crash-email, ERR-02 Resend-failure logging, ERR-03 corrupt-state surfacing → Phase 8.
- Dashboard HTML rendering → Phase 5.

All these are called out in ROADMAP.md §Phase Details for Phases 5/6/7/8 and REQUIREMENTS.md Traceability table, and were verified present by the Step 9b deferred-items scan.

---

*Verified: 2026-04-22T05:40:00+08:00*
*Verifier: Claude (gsd-verifier)*
