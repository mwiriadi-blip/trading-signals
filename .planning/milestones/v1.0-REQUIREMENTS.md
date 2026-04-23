# Requirements: Trading Signals — SPI 200 & AUD/USD Mechanical System

**Defined:** 2026-04-20
**Amended:** 2026-04-22 (CLI-01, CLI-03, CLI-05 Phase 4 ↔ Phase 6/7 split — per Phase 4 cross-AI review 04-REVIEWS.md C-1)
**Core Value:** Deliver an accurate, reproducible daily signal and actionable instruction to one email inbox every weekday at 08:00 AWST — with full state persistence so P&L, positions, and trade history survive restarts.

## v1 Requirements

Fine granularity — each requirement is independently testable.

### Data Ingestion

- [x] **DATA-01**: App fetches 400 days of daily OHLCV for `^AXJO` via yfinance
- [x] **DATA-02**: App fetches 400 days of daily OHLCV for `AUDUSD=X` via yfinance
- [x] **DATA-03**: Fetch retries up to 3 times with 10s backoff on failure
- [x] **DATA-04**: Empty/short frame (len < 300) raises a hard fail — no state written, error emailed
- [x] **DATA-05**: Stale last bar (older than per-instrument freshness budget) is flagged as a warning
- [x] **DATA-06**: `signal_as_of` (date of last data bar) is logged separately from `run_date` (clock-now in Perth)

### Signal Engine (pure math)

- [x] **SIG-01
**: ATR(14) computed via Wilder's `ewm(alpha=1/14, adjust=False, min_periods=14)`
- [x] **SIG-02
**: ADX(20) with +DI and -DI computed via Wilder's method, garbage bars return NaN
- [x] **SIG-03
**: Mom1 / Mom3 / Mom12 computed as 21 / 63 / 252-day price returns
- [x] **SIG-04
**: RVol computed as 20-day daily return std × √252
- [x] **SIG-05
**: Signal FLAT (0) when ADX < 25
- [x] **SIG-06
**: Signal LONG (1) when ADX ≥ 25 and ≥2 of [Mom1, Mom3, Mom12] > +0.02
- [x] **SIG-07
**: Signal SHORT (-1) when ADX ≥ 25 and ≥2 of [Mom1, Mom3, Mom12] < -0.02
- [x] **SIG-08
**: Signal FLAT (0) when ADX ≥ 25 but neither up nor down vote reaches 2

### Position Sizing

- [x] **SIZE-01
**: `risk_pct` = 1.0% for LONG, 0.5% for SHORT
- [x] **SIZE-02
**: `trail_mult` = 3.0 for LONG, 2.0 for SHORT
- [x] **SIZE-03
**: `vol_scale = clip(0.12 / RVol, 0.3, 2.0)` (guard RVol ≤ 1e-9 as 2.0)
- [x] **SIZE-04
**: `n_contracts = int((account × risk_pct / stop_dist) × vol_scale)` (no `max(1, …)` floor)
- [x] **SIZE-05
**: If sized `n_contracts == 0`, skip the trade and surface a "size=0" warning in the email
- [x] **SIZE-06
**: SPI multiplier $25/point, $30 AUD round-trip cost; AUD/USD $10,000 notional, $5 AUD round-trip cost

### Exit Rules

- [x] **EXIT-01
**: LONG→FLAT closes the open LONG (FLAT means "no position")
- [x] **EXIT-02
**: SHORT→FLAT closes the open SHORT
- [x] **EXIT-03
**: LONG→SHORT in one run closes LONG then opens SHORT (two-phase eval: exits before entries)
- [x] **EXIT-04
**: SHORT→LONG in one run closes SHORT then opens LONG
- [x] **EXIT-05
**: ADX < 20 while in trade closes the position immediately
- [x] **EXIT-06
**: LONG trailing stop = peak_price − (3 × ATR); peak updates with today's HIGH (intraday)
- [x] **EXIT-07
**: SHORT trailing stop = trough_price + (2 × ATR); trough updates with today's LOW (intraday)
- [x] **EXIT-08
**: LONG stop hit if today's LOW ≤ stop (intraday check)
- [x] **EXIT-09
**: SHORT stop hit if today's HIGH ≥ stop (intraday check)

### Pyramiding

- [x] **PYRA-01
**: Pyramid level persists in state per position
- [x] **PYRA-02
**: At level 0, adds 1 contract when unrealised ≥ 1 × ATR_entry → level 1
- [x] **PYRA-03
**: At level 1, adds 1 contract when unrealised ≥ 2 × ATR_entry → level 2
- [x] **PYRA-04
**: Never adds beyond 3 total contracts (level ≤ 2)
- [x] **PYRA-05
**: Maximum one pyramid step per daily run (no double-add on gap days)

### State Persistence

- [x] **STATE-01**: State file `state.json` has top-level keys: `schema_version`, `account`, `last_run`, `positions`, `signals`, `trade_log`, `equity_history`, `warnings`
- [x] **STATE-02**: Writes are atomic via tempfile → fsync → `os.replace`
- [x] **STATE-03**: Corrupt `state.json` is backed up to `state.json.corrupt.<timestamp>` and reinitialised
- [x] **STATE-04**: `schema_version` enables forward migration path (no-op migration on v1 to prove the hook)
- [x] **STATE-05**: `record_trade(state, trade)` appends to `trade_log` and adjusts `account`
- [x] **STATE-06**: `update_equity_history(state, date)` appends `{date, equity}` with equity = account + sum(unrealised)
- [x] **STATE-07**: `reset_state()` reinitialises account to $100,000 with empty positions/trades/history

### Email Notification

- [x] **NOTF-01**: Email sends via Resend HTTPS API (`POST https://api.resend.com/emails`) with Bearer token
- [x] **NOTF-02**: Subject shows signals + P&L + date, prefixed 🔴 on signal change and 📊 when unchanged
- [x] **NOTF-03**: HTML body uses inline CSS only (dark theme: #0f1117 bg, #22c55e LONG, #ef4444 SHORT, #eab308 FLAT)
- [x] **NOTF-04**: Body sections: header with date/account, signal status table, positions, today's P&L, running equity, last 5 closed trades, footer disclaimer
- [x] **NOTF-05**: ACTION REQUIRED block (red border) appears when any signal changed from the previous run
- [x] **NOTF-06**: Email is mobile-responsive (tested width 375px)
- [x] **NOTF-07**: Resend API failure logs error and continues — does NOT crash the workflow
- [x] **NOTF-08**: Missing `RESEND_API_KEY` degrades gracefully (writes `last_email.html` + console) — no crash
- [x] **NOTF-09**: All user-visible values in the HTML are escaped to prevent injection
- [x] **NOTF-10
**: Warnings from previous run carry over into next email header

### Dashboard

- [x] **DASH-01**: `dashboard.html` is a single self-contained file with inline CSS
- [x] **DASH-02**: Chart.js 4.4.6 UMD is loaded from a pinned CDN URL with SRI hash
- [x] **DASH-03**: Page shows current signal for both instruments with status colour
- [x] **DASH-04**: Account equity chart (Chart.js line) uses `equity_history` data
- [x] **DASH-05**: Open positions table shows entry, current, contracts, pyramid level, trail stop, unrealised P&L
- [x] **DASH-06**: Last 20 closed trades rendered as an HTML table
- [x] **DASH-07**: Key stats block shows total return, Sharpe, max drawdown, win rate
- [x] **DASH-08**: "Last updated" timestamp shown in AWST
- [x] **DASH-09**: Visual theme matches backtest aesthetic (same palette as email)

### Scheduler & Deployment

- [x] **SCHED-01
**: Scheduler fires at 08:00 AWST (00:00 UTC) weekdays Mon–Fri
- [x] **SCHED-02
**: Initial run executes immediately on process start (before schedule loop)
- [x] **SCHED-03
**: `run_daily_check` has an internal weekday gate (does not execute on Sat/Sun even if invoked)
- [x] **SCHED-04
**: `--once` flag runs a single daily check and exits (used by GitHub Actions)
- [x] **SCHED-05
**: Primary deployment is GitHub Actions: `.github/workflows/daily.yml` with `cron: '0 0 * * 1-5'`, `permissions: contents: write`, `concurrency: trading-signals`, and commit-back of `state.json` via `stefanzweifel/git-auto-commit-action@v5`
- [x] **SCHED-06
**: Alternative deployment is Replit Always On (Reserved VM), documented with filesystem-persistence caveat
- [x] **SCHED-07
**: All secrets loaded from env vars (`.env` locally, GitHub Secrets / Replit Secrets in deploy)

### CLI Flags

- [x] **CLI-01**: `python main.py --test` runs a full signal check, prints the report, sends a `[TEST]`-prefixed email, and does NOT mutate `state.json` (enforced by structurally separating compute and persist). **Phase 4 lands the compute + structural read-only guarantee + a `[Email] --test` stub log line; the actual `[TEST]`-prefixed Resend send is wired in Phase 6 (NOTF-01 dispatch point).** The structural read-only guarantee (no `state.json` mutation on `--test`) is satisfied in Phase 4 and does not change in Phase 6.
- [x] **CLI-02**: `python main.py --reset` reinitialises `state.json` after confirmation
- [x] **CLI-03**: `python main.py --force-email` sends today's email immediately regardless of schedule. **Phase 4 parses the flag and logs `[Email] --force-email received; notifier wiring arrives in Phase 6` (stub), honouring the `--test` + `--force-email` combination by running `run_daily_check` first without persist then emitting the stub; Phase 6 replaces the stub with `notifier.send_daily_email()` fed by fresh computed state (same compute path as `--once`).**
- [x] **CLI-04**: `python main.py --once` runs one daily check for GitHub Actions mode
- [x] **CLI-05**: Default invocation (`python main.py`) runs immediately and then enters the schedule loop. **Phase 4 lands default-mode == `--once` (runs once and exits; logs `[Sched] One-shot mode (scheduler wiring lands in Phase 7)`); Phase 7 flips default to run-once-then-enter-schedule-loop via the `schedule` library per SCHED-01
/02.**

### Error Handling & Observability

- [x] **ERR-01**: yfinance failure after 3 retries logs `[Fetch] ERROR <symbol>: <exception>` to stderr, exits with return code 2, and does NOT send email (deliberate — transient data-fetch errors are expected during weekly market closures, DNS blips, and upstream yfinance outages and should not spam the operator's inbox; only unhandled exceptions reach the Layer-B crash-email path via `main.py:1375-1398`). Guard: `tests/test_main.py::TestCrashEmailBoundary::test_data_fetch_error_does_not_fire_crash_email` locks the no-email behaviour.
- [x] **ERR-02
**: Resend API failure is logged, written to console, and does not crash the run
- [x] **ERR-03
**: Corrupt `state.json` is backed up and reinitialised with a warning in the next email
- [x] **ERR-04
**: Top-level `except Exception` wraps `run_daily_check`; crashes attempt a crash email then exit non-zero
- [x] **ERR-05
**: If `last_run` is > 2 days old on startup, the next email prefixes a "stale state" banner
- [x] **ERR-06**: Console logs use a structured format readable in Replit/GHA output (one block per instrument + summary)

### Configuration (added 2026-04-22 — folded in from pending todo, landing in Phase 8)

- [x] **CONF-01
**: Starting account amount is a runtime config entered at `--reset` (CLI flag `--initial-account <amount>`), persisted under `state['initial_account']`. Dashboard total-return formula (DASH-07) and Phase 6 email equity/P&L references read from `state['initial_account']` instead of the hardcoded `system_params.INITIAL_ACCOUNT`. Backward-compat: if the key is missing from a pre-existing state.json, default to `INITIAL_ACCOUNT` (current $100,000) via Phase 3's `_migrate` hook. Minimum: $1,000 (validated at CLI parse).
- [x] **CONF-02
**: Contract size is selectable per instrument via CLI flag (`--spi-contract {mini|standard|full}` and `--audusd-contract {standard|mini}`) at `--reset`, persisted under `state['contracts'][symbol]` as a preset label. Orchestrator reads the preset and passes the corresponding `multiplier` + `cost_aud` tier to `sizing_engine.step()` and `_closed_trade_to_record`. Tier table lives in `system_params.py` (`SPI_CONTRACTS`, `AUDUSD_CONTRACTS` dicts). Backward-compat: missing key defaults to `'mini'` (SPI: $5/pt $6 round-trip — current locked values per Phase 2 D-11).

## v2 Requirements

Deferred to future releases. Not in current roadmap.

### Reliability

- **V2-REL-01**: Timestamped `state.json` backups (`state.json.2026-04-20.bak`) + `--restore <timestamp>` flag
- **V2-REL-02**: `--dry-run` flag (compute + print, no write, no email)
- **V2-REL-03**: Signal history panel in dashboard (per-instrument ADX/Mom over time)

### Reporting

- **V2-REP-01**: `--export-trades` CSV export for tax time
- **V2-REP-02**: Weekly summary email (Sunday evening)

### Delivery

- **V2-DEL-01**: Slack webhook as secondary channel on ACTION REQUIRED days
- **V2-DEL-02**: Per-instrument mute flag to pause alerts during manual override

## Out of Scope

Explicitly excluded to prevent scope creep. These are hard anti-features for v1.

| Feature | Reason |
|---------|--------|
| Live order execution | Signal-only constraint — operator places trades manually |
| Additional instruments beyond SPI 200 and AUD/USD | Each new instrument needs its own backtest + contract-spec block; v1 proves the pattern |
| Intraday / tick-level signals | Different product; daily close only per system design |
| Weekly-cadence mode (Friday-close check, Monday-open execute) | Daily version is primary build target; weekly switch is a future milestone |
| Multi-user accounts / auth | Single-operator tool; Resend API key + Replit/GHA secrets are the gate |
| React / Vue / any SPA framework | Dashboard is one static HTML file by design |
| Database (SQLite / Postgres / Redis) | All state fits in one `state.json`; no shared-state need |
| Backtesting UI | Backtests done separately; this app only runs forward |
| Financial advice / regulatory disclosures | Footer disclaimer only; this is not a regulated service |
| News / sentiment / auto-tuning / broker integrations | Breaks determinism and changes the product shape |
| Push notifications / SMS | Email is sufficient for daily cadence |
| Chart overlays / candlestick rendering in dashboard | Equity curve + tables; richer charts are v2+ |

## Traceability

Updated during roadmap creation — each requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 4 | Complete |
| DATA-02 | Phase 4 | Complete |
| DATA-03 | Phase 4 | Complete |
| DATA-04 | Phase 4 | Complete |
| DATA-05 | Phase 4 | Complete |
| DATA-06 | Phase 4 | Complete |
| SIG-01 | Phase 1 | Complete (oracle Plan 01-02 + production Plan 01-04 @ 1e-9) |
| SIG-02 | Phase 1 | Complete (oracle Plan 01-02 + production Plan 01-04 @ 1e-9) |
| SIG-03 | Phase 1 | Complete (oracle Plan 01-02 + production Plan 01-04 @ 1e-9) |
| SIG-04 | Phase 1 | Complete (oracle Plan 01-02 + production Plan 01-04 @ 1e-9) |
| SIG-05 | Phase 1 | Complete (Plan 01-03 goldens + Plan 01-05 production SUT verified @ 1e-9) |
| SIG-06 | Phase 1 | Complete (Plan 01-03 goldens + Plan 01-05 production SUT verified @ 1e-9) |
| SIG-07 | Phase 1 | Complete (Plan 01-03 goldens + Plan 01-05 production SUT verified @ 1e-9) |
| SIG-08 | Phase 1 | Complete (Plan 01-03 goldens + Plan 01-05 production SUT verified @ 1e-9) |
| SIZE-01 | Phase 2 | Complete |
| SIZE-02 | Phase 2 | Complete |
| SIZE-03 | Phase 2 | Complete |
| SIZE-04 | Phase 2 | Complete |
| SIZE-05 | Phase 2 | Complete |
| SIZE-06 | Phase 2 | Complete |
| EXIT-01 | Phase 2 | Complete |
| EXIT-02 | Phase 2 | Complete |
| EXIT-03 | Phase 2 | Complete |
| EXIT-04 | Phase 2 | Complete |
| EXIT-05 | Phase 2 | Complete |
| EXIT-06 | Phase 2 | Complete |
| EXIT-07 | Phase 2 | Complete |
| EXIT-08 | Phase 2 | Complete |
| EXIT-09 | Phase 2 | Complete |
| PYRA-01 | Phase 2 | Complete |
| PYRA-02 | Phase 2 | Complete |
| PYRA-03 | Phase 2 | Complete |
| PYRA-04 | Phase 2 | Complete |
| PYRA-05 | Phase 2 | Complete |
| STATE-01 | Phase 3 | Complete |
| STATE-02 | Phase 3 | Complete |
| STATE-03 | Phase 3 | Complete |
| STATE-04 | Phase 3 | Complete |
| STATE-05 | Phase 3 | Complete |
| STATE-06 | Phase 3 | Complete |
| STATE-07 | Phase 3 | Complete |
| NOTF-01 | Phase 6 | Complete |
| NOTF-02 | Phase 6 | Complete |
| NOTF-03 | Phase 6 | Complete |
| NOTF-04 | Phase 6 | Complete |
| NOTF-05 | Phase 6 | Complete |
| NOTF-06 | Phase 6 | Complete |
| NOTF-07 | Phase 6 | Complete |
| NOTF-08 | Phase 6 | Complete |
| NOTF-09 | Phase 6 | Complete |
| NOTF-10 | Phase 8 | Complete |
| DASH-01 | Phase 5 | Complete |
| DASH-02 | Phase 5 | Complete |
| DASH-03 | Phase 5 | Complete |
| DASH-04 | Phase 5 | Complete |
| DASH-05 | Phase 5 | Complete |
| DASH-06 | Phase 5 | Complete |
| DASH-07 | Phase 5 | Complete |
| DASH-08 | Phase 5 | Complete |
| DASH-09 | Phase 5 | Complete |
| SCHED-01 | Phase 7 | Complete (Plan 07-02 _run_schedule_loop cron wiring + SCHEDULE_TIME_UTC 00:00) |
| SCHED-02 | Phase 7 | Complete (Plan 07-02 main() default dispatch: immediate first run before loop) |
| SCHED-03 | Phase 7 | Complete (Plan 07-02 run_daily_check weekday gate, WEEKDAY_SKIP_THRESHOLD=5) |
| SCHED-04 | Phase 7 | Complete (Plan 07-03 workflow `python main.py --once` step + CLI-04 preserved) |
| SCHED-05 | Phase 7 | Complete (Plan 07-03 .github/workflows/daily.yml, operator-verified 2026-04-23) |
| SCHED-06 | Phase 7 | Complete (Plan 07-03 docs/DEPLOY.md §Alternative — Reserved VM + Always On caveat) |
| SCHED-07 | Phase 7 | Complete (Plan 07-01 dotenv bootstrap + Plan 07-03 GHA Secrets + Replit Secrets docs) |
| CLI-01 | Phase 4 (compute + structural read-only) + Phase 6 (`[TEST]` email wiring) | Complete |
| CLI-02 | Phase 4 | Complete |
| CLI-03 | Phase 4 (stub + `--test` combo) + Phase 6 (notifier wiring) | Complete |
| CLI-04 | Phase 4 | Complete |
| CLI-05 | Phase 4 (default == one-shot) + Phase 7 (schedule-loop wiring) | Complete |
| ERR-01 | Phase 4 | Complete (spec amended in Phase 9 to match `test_data_fetch_error_does_not_fire_crash_email` lock) |
| ERR-02 | Phase 8 | Complete |
| ERR-03 | Phase 8 | Complete |
| ERR-04 | Phase 8 | Complete |
| ERR-05 | Phase 8 | Complete |
| ERR-06 | Phase 4 | Complete |
| CONF-01 | Phase 8 | Complete |
| CONF-02 | Phase 8 | Complete |

**Coverage:**
- v1 requirements: 80 total (DATA 6 + SIG 8 + SIZE 6 + EXIT 9 + PYRA 5 + STATE 7 + NOTF 10 + DASH 9 + SCHED 7 + CLI 5 + ERR 6 + CONF 2)
- Mapped to phases: 80/80, Verified: 80/80
- Unmapped: 0
- Note (2026-04-22): CLI-01, CLI-03, and CLI-05 are split across phases — Phase 4 owns the CLI surface + compute + structural guarantees; Phase 6 owns Resend dispatch (CLI-01 `[TEST]` send + CLI-03 today's email); Phase 7 owns the schedule loop (CLI-05 default-mode loop). Each split is tracked in the per-phase requirement lists; coverage is still 1:1 at the phase-requirement-closure level.
- Note (2026-04-22): CONF-01 and CONF-02 added by folding a pending todo ("Configurable starting account and contract sizes") into Phase 8 Hardening. Phase 8 req count now 7 (was 5).

**Per-phase counts:**
- Phase 1 (Signal Engine Core): 8 reqs
- Phase 2 (Sizing/Exits/Pyramiding): 20 reqs
- Phase 3 (State Persistence): 7 reqs
- Phase 4 (E2E Skeleton): 13 reqs
- Phase 5 (Dashboard): 9 reqs
- Phase 6 (Email Notification): 9 reqs
- Phase 7 (Scheduler + Deploy): 7 reqs
- Phase 8 (Hardening): 7 reqs (5 original + CONF-01 + CONF-02 added 2026-04-22)
- **Total: 80**

---
*Requirements defined: 2026-04-20*
*Traceability populated: 2026-04-20 (roadmap creation)*
*Amended 2026-04-22: CLI-01 / CLI-03 / CLI-05 Phase 4 ↔ Phase 6/7 split per Phase 4 cross-AI review (04-REVIEWS.md C-1) — Phase 4 owns CLI surface, compute, and structural read-only guarantee; Phase 6 wires email dispatch; Phase 7 wires schedule loop.*
*Amended 2026-04-23: Phase 9 gap closure — ERR-01 spec text reconciled with implemented + test-locked no-email-on-data-error design; all 80 traceability checkboxes flipped to [x]/Complete to reflect v1.0-MILESTONE-AUDIT.md verified state (79/80 VERIFIED + 1 amended = 80/80).*
