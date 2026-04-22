# Roadmap: Trading Signals — SPI 200 & AUD/USD Mechanical System

**Created:** 2026-04-20
**Amended:** 2026-04-22 (Phase 4 SC-5 wording — per Phase 4 cross-AI review 04-REVIEWS.md C-1)
**Granularity:** fine
**Parallelization:** true
**Coverage:** 80/80 v1 requirements mapped (was 78; +2 CONF-01/02 folded into Phase 8 on 2026-04-22)

**Core Value:** Deliver an accurate, reproducible daily signal and actionable instruction to one email inbox every weekday at 08:00 AWST — with full state persistence so P&L, positions, and trade history survive restarts.

## Phases

- [x] **Phase 1: Signal Engine Core — Indicators & Vote** — Pure-math indicator library (ATR/ADX/Mom/RVol) and the 2-of-3 momentum vote with ADX gate, fixture-tested (completed 2026-04-20)
- [ ] **Phase 2: Signal Engine — Sizing, Exits, Pyramiding** — Pure-math position sizing (skip-if-zero), exit rules (intraday H/L), and pyramid state machine, fixture-tested
- [x] **Phase 3: State Persistence with Recovery** — `state_manager.py` with atomic writes, corruption recovery, and schema versioning (completed 2026-04-21)
- [x] **Phase 4: End-to-End Skeleton — Fetch + Orchestrator + CLI** — Live yfinance fetch, `main.py` orchestrator, CLI flags, structured logs (completed 2026-04-22)
- [x] **Phase 5: Dashboard** — Static `dashboard.html` with Chart.js equity curve, positions, trades, key stats (completed 2026-04-22)
- [ ] **Phase 6: Email Notification** — Resend HTML email with ACTION REQUIRED block, mobile-responsive dark theme, graceful degradation
- [ ] **Phase 7: Scheduler + GitHub Actions Deployment** — `cron 0 0 * * 1-5` GHA workflow with state commit-back, Replit alternative documented
- [ ] **Phase 8: Hardening — Warning Carry-over, Stale Banner, Crash Email, Configurable Account** — Warning persistence, stale-state banner, top-level crash path, corrupt-state recovery surfaced to operator, configurable starting account + per-instrument contract-size tiers (CONF-01/02 folded in 2026-04-22)

## Phase Details

### Phase 1: Signal Engine Core — Indicators & Vote
**Goal**: Produce deterministic indicator values and a LONG/SHORT/FLAT signal for any given OHLCV fixture — zero I/O, zero network, fully golden-file tested.
**Depends on**: Nothing (first phase; parallelable with Phase 3)
**Requirements**: SIG-01, SIG-02, SIG-03, SIG-04, SIG-05, SIG-06, SIG-07, SIG-08
**Success Criteria** (what must be TRUE):
  1. Given a committed 400-bar CSV fixture, ATR(14), ADX(20), +DI, -DI, Mom1, Mom3, Mom12, and RVol(20) match hand-calculated golden values to 1e-9 tolerance
  2. ADX < 25 on any fixture returns signal 0 (FLAT) regardless of momentum values
  3. ADX ≥ 25 with ≥2 of [Mom1, Mom3, Mom12] above +0.02 returns signal 1 (LONG); mirror case returns -1 (SHORT); split vote returns 0 (FLAT)
  4. Warm-up bars (first N-1 of each indicator) return NaN, not zero or garbage, via `min_periods=period`
  5. `pytest tests/test_signal_engine.py -k indicators_or_vote` passes green with zero network calls
**Plans:** 6/6 plans complete
- [x] 01-01-PLAN.md — Wave 0 scaffold: Python 3.11 venv, pinned requirements.txt (R-02), pyproject.toml with pytest + ruff config (R-05), CLAUDE.md stack amendment, test-package skeleton, oracle README
- [x] 01-02-PLAN.md — Wave 1: pure-Python-loop Wilder oracle (ATR, ADX, +DI, -DI, Mom, RVol) + oracle self-consistency tests per D-02
- [x] 01-03-PLAN.md — Wave 1 (parallel): canonical fixtures for ^AXJO + AUDUSD=X (R-03), 9 scenario fixtures (D-16), regenerate_goldens.py + initial goldens + determinism snapshot
- [x] 01-04-PLAN.md — Wave 2: signal_engine.py compute_indicators + private helpers; TestIndicators class proves SIG-01..04 match oracle to 1e-9 on both canonical fixtures
- [x] 01-05-PLAN.md — Wave 3 (after 04; both share signal_engine.py): signal_engine.py get_signal + get_latest_indicators; TestVote + TestEdgeCases classes prove SIG-05..08 + D-09..12 via 9 scenario fixtures
- [x] 01-06-PLAN.md — Wave 4: TestDeterminism class (SHA256 snapshot regression + architectural AST guards); full phase gate
**UI hint**: no

### Phase 2: Signal Engine — Sizing, Exits, Pyramiding
**Goal**: Produce deterministic position sizes, exit decisions, and pyramid-level transitions for any given (state, indicators, today's bar) input — pure functions, fixture-tested, with the 9-cell signal-transition truth table locked down.
**Depends on**: Phase 1
**Requirements**: SIZE-01, SIZE-02, SIZE-03, SIZE-04, SIZE-05, SIZE-06, EXIT-01, EXIT-02, EXIT-03, EXIT-04, EXIT-05, EXIT-06, EXIT-07, EXIT-08, EXIT-09, PYRA-01, PYRA-02, PYRA-03, PYRA-04, PYRA-05
**Success Criteria** (what must be TRUE):
  1. `n_contracts == 0` after vol-scale clip returns a skip-trade decision with a "size=0" warning string, no `max(1, …)` floor applied
  2. The full 9-cell signal-transition matrix ({LONG, SHORT, none} × {LONG, SHORT, FLAT}) produces the right exit-then-entry sequence — LONG→FLAT closes, LONG→SHORT closes then reopens SHORT in one run
  3. Trailing stop updates peak with today's HIGH (LONG) and trough with today's LOW (SHORT); stop hits when today's LOW ≤ LONG stop or today's HIGH ≥ SHORT stop
  4. Given a gap-up fixture crossing both +1×ATR and +2×ATR in one bar, pyramid level advances by exactly 1 (not 2), and never exceeds level 2 (3 total contracts)
  5. ADX < 20 while in an active position produces an immediate-close decision regardless of trailing-stop state
**Plans:** 5 plans
- [x] 02-01-PLAN.md — Wave 0 BLOCKING scaffold: SPEC.md/CLAUDE.md amendments (D-11/D-07), system_params.py + sizing_engine.py stubs + tests/test_sizing_engine.py skeleton, AST blocklist extension, Phase 1 constant migration
- [x] 02-02-PLAN.md — Wave 1: calc_position_size + compute_unrealised_pnl + TestSizing (SIZE-01..06)
- [x] 02-03-PLAN.md — Wave 2: get_trailing_stop + check_stop_hit + check_pyramid + TestExits + TestPyramid (EXIT-06..09, PYRA-01..05)
- [x] 02-04-PLAN.md — Wave 3: 15 JSON scenario fixtures + regenerator + TestTransitions + TestEdgeCases (EXIT-01..09, PYRA-05, SIZE-05 via scenarios)
- [x] 02-05-PLAN.md — Wave 4 (phase gate): step() orchestrator + position_after fixture re-emission + phase2_snapshot.json + TestStep + TestDeterminism extension (D-06)
**UI hint**: no

### Phase 3: State Persistence with Recovery
**Goal**: Provide a `state_manager.py` module the orchestrator can rely on to load, mutate, and save state durably — with crash-mid-write protection, corruption recovery, and a schema-version hook ready for v2 migrations.
**Depends on**: Nothing (parallelable with Phases 1–2)
**Requirements**: STATE-01, STATE-02, STATE-03, STATE-04, STATE-05, STATE-06, STATE-07
**Success Criteria** (what must be TRUE):
  1. A freshly-initialised `state.json` contains all top-level keys: `schema_version`, `account`, `last_run`, `positions`, `signals`, `trade_log`, `equity_history`, `warnings`
  2. A simulated crash between `tempfile.write` and `os.replace` leaves the original `state.json` intact and readable
  3. A deliberately corrupted `state.json` is moved to `state.json.corrupt.<timestamp>` and a fresh state is written, with no exception propagated to the caller
  4. `record_trade(state, trade)` appends to `trade_log` and adjusts `account` consistent with the trade P&L; `update_equity_history` appends `{date, equity}` where equity = account + sum(unrealised)
  5. `reset_state()` reinitialises account to $100,000 with empty positions, trades, and history, and passes the schema-version migration hook (no-op at v1)
**Plans:** 4/4 plans complete
- [x] 03-01-PLAN.md — Wave 0 BLOCKING scaffold: system_params.py constants (INITIAL_ACCOUNT, MAX_WARNINGS, STATE_SCHEMA_VERSION, STATE_FILE), state_manager.py + tests/test_state_manager.py stubs, AST blocklist extension for I/O hex
- [x] 03-02-PLAN.md — Wave 1: _atomic_write + save_state + _migrate + happy-path load_state; TestLoadSave + TestAtomicity + TestSchemaVersion (STATE-02, STATE-04)
- [x] 03-03-PLAN.md — Wave 2: reset_state + corruption recovery + append_warning; TestReset + TestCorruptionRecovery + TestWarnings (STATE-01, STATE-03, STATE-07)
- [x] 03-04-PLAN.md — Wave 3 (phase gate): _validate_trade + record_trade + update_equity_history; TestRecordTrade (incl. CRITICAL Phase 4 boundary AC) + TestEquityHistory (STATE-05, STATE-06)
**UI hint**: no

### Phase 4: End-to-End Skeleton — Fetch + Orchestrator + CLI
**Goal**: Wire the signal engine and state manager together behind a real yfinance fetch, with CLI flags, structured logs, and a top-level error boundary — `python main.py --once` reads Yahoo, computes signals, updates state, and prints a readable console summary. No email, no dashboard yet.
**Depends on**: Phase 1, Phase 2, Phase 3
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, ERR-01, ERR-06
**Success Criteria** (what must be TRUE):
  1. `python main.py --once` fetches 400 days of OHLCV for `^AXJO` and `AUDUSD=X`, retries up to 3× with 10s backoff on failure, and prints a structured per-instrument log block plus a run summary
  2. A short/empty frame (len < 300) hard-fails the run — no state written, error logged, exit non-zero; stale last-bar is logged as a warning but not fatal
  3. `signal_as_of` (last data-bar date) and `run_date` (Perth clock-now) are both logged on every run and never substituted for each other
  4. `python main.py --test` produces the full computed summary and leaves `state.json` mtime unchanged (structurally separated compute vs persist)
  5. `python main.py --reset` reinitialises state after confirmation; `python main.py --once` exits cleanly for GHA use; default `python main.py` runs once and exits in Phase 4 (schedule-loop wiring lands in Phase 7 per SCHED-01/02; `--force-email` and `--test`-email are stubbed in Phase 4 and wired in Phase 6 per NOTF-01)
**Plans:** 4/4 plans complete
- [x] 04-01-PLAN.md — Wave 0 BLOCKING scaffold: data_fetcher.py + main.py stubs, tests/test_data_fetcher.py + tests/test_main.py skeletons, tests/regenerate_fetch_fixtures.py + committed JSON fixtures, AST blocklist extension, pytest-freezer pin, REQUIREMENTS.md + ROADMAP.md amendments per Phase 4 cross-AI review
- [x] 04-02-PLAN.md — Wave 1: data_fetcher.fetch_ohlcv with yfinance retry loop + TestFetch + TestColumnShape (DATA-01/02/03) + TestColumnShape missing-required-columns test
- [x] 04-03-PLAN.md — Wave 2: run_daily_check D-11 sequence + _closed_trade_to_record + D-08 backward-compat + TestOrchestrator happy-path + TestCLI smoke tests (DATA-04/06, CLI-04/05, ERR-06, D-08/D-12, reversal-ordering AC-1)
- [x] 04-04-PLAN.md — Wave 3 (PHASE GATE): top-level exception boundary + --reset confirmation + --force-email stub + DATA-05 stale-bar detection + TestCLI CLI-01/02/03 + TestOrchestrator DATA-05/ERR-01 + TestLoggerConfig (Pitfall 4)
**UI hint**: no

### Phase 5: Dashboard
**Goal**: Render a self-contained `dashboard.html` each run that lets the operator visually verify signal state, open positions, equity history, and recent trades — matching the backtest dark aesthetic.
**Depends on**: Phase 4 (needs real state written)
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06, DASH-07, DASH-08, DASH-09
**Success Criteria** (what must be TRUE):
  1. `dashboard.html` opens standalone in a browser, renders with inline CSS (no external stylesheet), and shows current signal status for both instruments with the correct colour (#22c55e LONG / #ef4444 SHORT / #eab308 FLAT)
  2. Chart.js 4.4.6 UMD loads from the pinned CDN URL with SRI hash and renders a non-blank equity curve from `equity_history`
  3. Open positions table shows entry, current, contracts, pyramid level, trail stop, and unrealised P&L; closed-trades table shows the last 20 trades
  4. Key stats block computes total return, Sharpe, max drawdown, and win rate from `equity_history` + `trade_log`
  5. "Last updated" timestamp is rendered in AWST (Australia/Perth)
**Plans:** 3/3 plans complete
- [x] 05-01-PLAN.md — Wave 0 BLOCKING scaffold: dashboard.py stub module + palette/Chart.js SRI constants + _INLINE_CSS scaffold; tests/test_dashboard.py 6-class skeleton; tests/fixtures/dashboard/ (sample_state.json + empty_state.json + placeholder goldens); tests/regenerate_dashboard_golden.py; AST blocklist extension (FORBIDDEN_MODULES_DASHBOARD); B-1 retrofit in main.py:514-519 (add last_close to signal dict) + test_main.py extension
- [x] 05-02-PLAN.md — Wave 1: stats math (Sharpe/MaxDD/WinRate/TotalReturn) + inline unrealised-P&L + trail-stop display math (hex-safe re-impl) + 6 formatters (currency/percent/P&L colour/em-dash/AWST last-updated) + 6 per-block renderers (header/signal_cards/positions_table/trades_table/key_stats/footer); populate TestStatsMath + TestFormatters + TestRenderBlocks
- [x] 05-03-PLAN.md — Wave 2 (PHASE GATE): Chart.js container with SRI + </script> injection defence + HTML shell + atomic write (mirror state_manager._atomic_write) + render_dashboard public API + full _INLINE_CSS stylesheet; regenerate golden fixtures (byte-stable double-run); D-06 main.py integration (never-crash try/except) + 4 orchestrator tests (render-happens + runtime-failure-isolated + import-time-failure-isolated + --test mtime invariant); populate TestEmptyState + TestGoldenSnapshot + TestAtomicWrite
**UI hint**: no

### Phase 6: Email Notification
**Goal**: Send a daily Resend email with signal status, positions, P&L, and an ACTION REQUIRED block when any signal has changed — mobile-responsive, inline-CSS, escaped values, and graceful degradation when Resend is unavailable. Also replaces the Phase 4 `--test` and `--force-email` log-line stubs with real Resend dispatch (CLI-01 `[TEST]`-prefixed email + CLI-03 today's email fed by fresh `run_daily_check` output).
**Depends on**: Phase 4 (needs state + signals to report)
**Requirements**: NOTF-01, NOTF-02, NOTF-03, NOTF-04, NOTF-05, NOTF-06, NOTF-07, NOTF-08, NOTF-09
**Success Criteria** (what must be TRUE):
  1. A live Resend `POST https://api.resend.com/emails` with Bearer token delivers an email whose subject shows signals + P&L + date and is prefixed 🔴 on signal change or 📊 when unchanged
  2. The HTML body renders correctly at 375px viewport with dark theme (#0f1117 bg), uses only inline CSS, and contains header, signal table, positions, today's P&L, running equity, last 5 closed trades, and footer disclaimer
  3. When any signal differs from the previous run's, an ACTION REQUIRED block with red border appears at the top of the body
  4. All user-visible values (numbers, dates, position fields) are HTML-escaped; no unescaped `${…}` interpolation present
  5. Missing `RESEND_API_KEY` writes `last_email.html` + console output and exits the notifier cleanly; a 4xx/5xx from Resend logs an error but does not crash the run
  6. `--force-email` dispatch (CLI-03 Phase 6 completion): `main()` replaces the Phase 4 stub with `rc = run_daily_check(args); if rc == 0: notifier.send_daily_email(...); return rc` — same fresh-compute-then-dispatch pattern as `--once`, but without persisting state when combined with `--test`.
  7. `--test` email dispatch (CLI-01 Phase 6 completion): same fresh-compute-then-dispatch pattern with a `[TEST]`-prefixed subject; the Phase 4 structural read-only guarantee on `state.json` (no mutation under `--test`) remains intact.
**Plans**: TBD
**UI hint**: no

### Phase 7: Scheduler + GitHub Actions Deployment
**Goal**: Put the system on autopilot — a GitHub Actions cron workflow runs the app every weekday at 00:00 UTC (08:00 AWST) and commits `state.json` back to the repo; the `schedule` loop path is preserved for Replit/local dev with a weekday gate inside `run_daily_check`. Also flips the Phase 4 default-mode behaviour from one-shot to run-once-then-enter-schedule-loop (CLI-05 Phase 7 completion).
**Depends on**: Phase 6 (needs full outputs working before lights-out)
**Requirements**: SCHED-01, SCHED-02, SCHED-03, SCHED-04, SCHED-05, SCHED-06, SCHED-07
**Success Criteria** (what must be TRUE):
  1. `.github/workflows/daily.yml` runs on `cron: '0 0 * * 1-5'` with `permissions: contents: write`, a `concurrency: trading-signals` block, `actions/checkout@v4`, `actions/setup-python@v5`, and `stefanzweifel/git-auto-commit-action@v5` to commit `state.json`
  2. The default `python main.py` entry point runs an immediate first check then enters the `schedule` loop firing at 00:00 UTC weekdays; `run_daily_check` has an internal weekday gate that no-ops on Sat/Sun even if invoked (replaces the Phase 4 default-mode == `--once` behaviour per CLI-05)
  3. `python main.py --once` runs exactly one check and exits cleanly with non-zero on failure — the GHA workflow uses this mode
  4. All secrets (`RESEND_API_KEY`, optional `ANTHROPIC_API_KEY`) are loaded from env vars with `python-dotenv` locally and GitHub Secrets / Replit Secrets in deploy — never committed
  5. Deployment guide documents GitHub Actions as the recommended primary path with Replit Reserved VM + Always On as the documented alternative including its filesystem-persistence caveat
**Plans**: TBD
**UI hint**: no

### Phase 8: Hardening — Warning Carry-over, Stale Banner, Crash Email, Configurable Account
**Goal**: Close the "looks done but isn't" gap — make sure warnings from any run surface in the next email, a dead scheduler is loudly visible, corrupt-state recovery is announced to the operator, any unhandled exception attempts one last crash email before exit, AND the operator can configure starting account + contract-size tiers at `--reset` time so the system works for real broker situations (not just SPI mini + $100k).
**Depends on**: Phase 7 (post-shipping hardening against real failure modes)
**Requirements**: NOTF-10, ERR-02, ERR-03, ERR-04, ERR-05, CONF-01, CONF-02
**Success Criteria** (what must be TRUE):
  1. Warnings appended to `state.warnings` in run N appear as a highlighted banner in the run-(N+1) email header, then are cleared after that email sends
  2. If `last_run` is > 2 days old on startup, the next email is prefixed with a visible "stale state" banner naming the gap in days
  3. A deliberately injected unhandled exception inside `run_daily_check` triggers the top-level `except Exception` handler, attempts one crash-email POST to Resend, logs the error, and exits non-zero
  4. A corrupt `state.json` (recovered via Phase 3's backup + reinit path) surfaces a warning in the next email that the state was reset, including the backup filename
  5. A failed Resend POST (simulated 5xx) is logged to the console with the status code and body excerpt, and the workflow continues to the next step without crashing
  6. `python main.py --reset --initial-account 50000` initialises state with `state['initial_account'] = 50000`; dashboard total-return formula + email equity references read from `state['initial_account']` instead of the hardcoded `system_params.INITIAL_ACCOUNT`; a pre-existing state.json without the key defaults to $100,000 via Phase 3's `_migrate` hook (backward-compat)
  7. `python main.py --reset --spi-contract standard --audusd-contract standard` persists per-instrument contract tiers into `state['contracts']`; orchestrator reads the preset at each run and passes the corresponding multiplier + cost to sizing functions; tier presets live in `system_params.py` (`SPI_CONTRACTS = {'mini': {m:5, cost:6}, 'standard': {m:25, cost:30}, 'full': {m:50, cost:50}}`, `AUDUSD_CONTRACTS = {...}`); missing key defaults to `'mini'` for SPI (per Phase 2 D-11 locked values)
**Plans**: TBD
**UI hint**: no

## Phase Dependencies (build order)

```
Phase 1 ─┐
         ├─► Phase 2 ─┐
Phase 3 ─┤            ├─► Phase 4 ─┬─► Phase 5 ─┐
         │            │            │            ├─► Phase 7 ─► Phase 8
         │            │            └─► Phase 6 ─┘
         └────────────┘
```

**Parallelizable pairs** (from config `parallelization: true`):
- Phases 1 and 3 can run in parallel (no shared code)
- Phases 5 and 6 can run in parallel (no shared code; both only read state)
- Phase 2 must follow Phase 1 (shares indicator contracts)

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Signal Engine Core — Indicators & Vote | 6/6 | Complete    | 2026-04-20 |
| 2. Signal Engine — Sizing, Exits, Pyramiding | 0/5 | Planned | - |
| 3. State Persistence with Recovery | 0/4 | Planned | - |
| 4. End-to-End Skeleton — Fetch + Orchestrator + CLI | 0/0 | Not started | - |
| 5. Dashboard | 0/0 | Not started | - |
| 6. Email Notification | 0/0 | Not started | - |
| 7. Scheduler + GitHub Actions Deployment | 0/0 | Not started | - |
| 8. Hardening — Warning Carry-over, Stale Banner, Crash Email | 0/0 | Not started | - |

## Coverage Validation

- **Total v1 requirements:** 80 (was 78 until 2026-04-22; +2 CONF reqs folded into Phase 8 from pending todo — now 12 categories: DATA 6, SIG 8, SIZE 6, EXIT 9, PYRA 5, STATE 7, NOTF 10, DASH 9, SCHED 7, CLI 5, ERR 6, CONF 2)
- **Mapped to phases:** 80/80
- **Orphans:** 0
- **Duplicates:** 0
- **Split requirements (2026-04-22 amendment):** CLI-01 (Phase 4 structural + Phase 6 email), CLI-03 (Phase 4 stub + Phase 6 notifier), CLI-05 (Phase 4 one-shot default + Phase 7 schedule loop) — tracked in REQUIREMENTS.md Traceability table with split phase labels.

## Operator Decisions Baked In

| Decision | Reflected in |
|----------|--------------|
| GitHub Actions is the PRIMARY deployment path | Phase 7 goal + SCHED-05 success criterion |
| `n_contracts == 0` skips trade + warns (no `max(1,…)` floor) | Phase 2 success criterion 1 + SIZE-04/05 |
| LONG→FLAT (and SHORT→FLAT) closes the open position | Phase 2 success criterion 2 + EXIT-01/02 |
| Trailing stops use intraday high/low (peak updates + hit detection) | Phase 2 success criterion 3 + EXIT-06/07/08/09 |

---
*Roadmap created: 2026-04-20*
*Amended 2026-04-22: Phase 4 SC-5 wording — default mode is one-shot in Phase 4; schedule-loop wiring lands in Phase 7 (per Phase 4 cross-AI review 04-REVIEWS.md C-1). Phase 6 goal + SC-6/SC-7 extended to cover CLI-01/CLI-03 Resend dispatch. Phase 7 goal + SC-2 extended to cover CLI-05 default-mode flip.*
*Ready for: `/gsd-plan-phase 1` (or parallel `/gsd-plan-phase 3`)*
