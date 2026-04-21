# Requirements: Trading Signals — SPI 200 & AUD/USD Mechanical System

**Defined:** 2026-04-20
**Core Value:** Deliver an accurate, reproducible daily signal and actionable instruction to one email inbox every weekday at 08:00 AWST — with full state persistence so P&L, positions, and trade history survive restarts.

## v1 Requirements

Fine granularity — each requirement is independently testable.

### Data Ingestion

- [ ] **DATA-01**: App fetches 400 days of daily OHLCV for `^AXJO` via yfinance
- [ ] **DATA-02**: App fetches 400 days of daily OHLCV for `AUDUSD=X` via yfinance
- [ ] **DATA-03**: Fetch retries up to 3 times with 10s backoff on failure
- [ ] **DATA-04**: Empty/short frame (len < 300) raises a hard fail — no state written, error emailed
- [ ] **DATA-05**: Stale last bar (older than per-instrument freshness budget) is flagged as a warning
- [ ] **DATA-06**: `signal_as_of` (date of last data bar) is logged separately from `run_date` (clock-now in Perth)

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

- [ ] **STATE-01**: State file `state.json` has top-level keys: `schema_version`, `account`, `last_run`, `positions`, `signals`, `trade_log`, `equity_history`, `warnings`
- [ ] **STATE-02**: Writes are atomic via tempfile → fsync → `os.replace`
- [ ] **STATE-03**: Corrupt `state.json` is backed up to `state.json.corrupt.<timestamp>` and reinitialised
- [ ] **STATE-04**: `schema_version` enables forward migration path (no-op migration on v1 to prove the hook)
- [ ] **STATE-05**: `record_trade(state, trade)` appends to `trade_log` and adjusts `account`
- [ ] **STATE-06**: `update_equity_history(state, date)` appends `{date, equity}` with equity = account + sum(unrealised)
- [ ] **STATE-07**: `reset_state()` reinitialises account to $100,000 with empty positions/trades/history

### Email Notification

- [ ] **NOTF-01**: Email sends via Resend HTTPS API (`POST https://api.resend.com/emails`) with Bearer token
- [ ] **NOTF-02**: Subject shows signals + P&L + date, prefixed 🔴 on signal change and 📊 when unchanged
- [ ] **NOTF-03**: HTML body uses inline CSS only (dark theme: #0f1117 bg, #22c55e LONG, #ef4444 SHORT, #eab308 FLAT)
- [ ] **NOTF-04**: Body sections: header with date/account, signal status table, positions, today's P&L, running equity, last 5 closed trades, footer disclaimer
- [ ] **NOTF-05**: ACTION REQUIRED block (red border) appears when any signal changed from the previous run
- [ ] **NOTF-06**: Email is mobile-responsive (tested width 375px)
- [ ] **NOTF-07**: Resend API failure logs error and continues — does NOT crash the workflow
- [ ] **NOTF-08**: Missing `RESEND_API_KEY` degrades gracefully (writes `last_email.html` + console) — no crash
- [ ] **NOTF-09**: All user-visible values in the HTML are escaped to prevent injection
- [ ] **NOTF-10**: Warnings from previous run carry over into next email header

### Dashboard

- [ ] **DASH-01**: `dashboard.html` is a single self-contained file with inline CSS
- [ ] **DASH-02**: Chart.js 4.4.6 UMD is loaded from a pinned CDN URL with SRI hash
- [ ] **DASH-03**: Page shows current signal for both instruments with status colour
- [ ] **DASH-04**: Account equity chart (Chart.js line) uses `equity_history` data
- [ ] **DASH-05**: Open positions table shows entry, current, contracts, pyramid level, trail stop, unrealised P&L
- [ ] **DASH-06**: Last 20 closed trades rendered as an HTML table
- [ ] **DASH-07**: Key stats block shows total return, Sharpe, max drawdown, win rate
- [ ] **DASH-08**: "Last updated" timestamp shown in AWST
- [ ] **DASH-09**: Visual theme matches backtest aesthetic (same palette as email)

### Scheduler & Deployment

- [ ] **SCHED-01**: Scheduler fires at 08:00 AWST (00:00 UTC) weekdays Mon–Fri
- [ ] **SCHED-02**: Initial run executes immediately on process start (before schedule loop)
- [ ] **SCHED-03**: `run_daily_check` has an internal weekday gate (does not execute on Sat/Sun even if invoked)
- [ ] **SCHED-04**: `--once` flag runs a single daily check and exits (used by GitHub Actions)
- [ ] **SCHED-05**: Primary deployment is GitHub Actions: `.github/workflows/daily.yml` with `cron: '0 0 * * 1-5'`, `permissions: contents: write`, `concurrency: trading-signals`, and commit-back of `state.json` via `stefanzweifel/git-auto-commit-action@v5`
- [ ] **SCHED-06**: Alternative deployment is Replit Always On (Reserved VM), documented with filesystem-persistence caveat
- [ ] **SCHED-07**: All secrets loaded from env vars (`.env` locally, GitHub Secrets / Replit Secrets in deploy)

### CLI Flags

- [ ] **CLI-01**: `python main.py --test` runs a full signal check, prints the report, sends a `[TEST]`-prefixed email, and does NOT mutate `state.json` (enforced by structurally separating compute and persist)
- [ ] **CLI-02**: `python main.py --reset` reinitialises `state.json` after confirmation
- [ ] **CLI-03**: `python main.py --force-email` sends today's email immediately regardless of schedule
- [ ] **CLI-04**: `python main.py --once` runs one daily check for GitHub Actions mode
- [ ] **CLI-05**: Default invocation (`python main.py`) runs immediately and then enters the schedule loop

### Error Handling & Observability

- [ ] **ERR-01**: yfinance failure after 3 retries sends an error email and exits gracefully
- [ ] **ERR-02**: Resend API failure is logged, written to console, and does not crash the run
- [ ] **ERR-03**: Corrupt `state.json` is backed up and reinitialised with a warning in the next email
- [ ] **ERR-04**: Top-level `except Exception` wraps `run_daily_check`; crashes attempt a crash email then exit non-zero
- [ ] **ERR-05**: If `last_run` is > 2 days old on startup, the next email prefixes a "stale state" banner
- [ ] **ERR-06**: Console logs use a structured format readable in Replit/GHA output (one block per instrument + summary)

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
| DATA-01 | Phase 4 | Pending |
| DATA-02 | Phase 4 | Pending |
| DATA-03 | Phase 4 | Pending |
| DATA-04 | Phase 4 | Pending |
| DATA-05 | Phase 4 | Pending |
| DATA-06 | Phase 4 | Pending |
| SIG-01 | Phase 1 | Complete (oracle Plan 01-02 + production Plan 01-04 @ 1e-9) |
| SIG-02 | Phase 1 | Complete (oracle Plan 01-02 + production Plan 01-04 @ 1e-9) |
| SIG-03 | Phase 1 | Complete (oracle Plan 01-02 + production Plan 01-04 @ 1e-9) |
| SIG-04 | Phase 1 | Complete (oracle Plan 01-02 + production Plan 01-04 @ 1e-9) |
| SIG-05 | Phase 1 | Goldens ready (Plan 01-03); production SUT pending (Plan 01-05) |
| SIG-06 | Phase 1 | Goldens ready (Plan 01-03); production SUT pending (Plan 01-05) |
| SIG-07 | Phase 1 | Goldens ready (Plan 01-03); production SUT pending (Plan 01-05) |
| SIG-08 | Phase 1 | Goldens ready (Plan 01-03); production SUT pending (Plan 01-05) |
| SIZE-01 | Phase 2 | Pending |
| SIZE-02 | Phase 2 | Pending |
| SIZE-03 | Phase 2 | Pending |
| SIZE-04 | Phase 2 | Pending |
| SIZE-05 | Phase 2 | Pending |
| SIZE-06 | Phase 2 | Pending |
| EXIT-01 | Phase 2 | Pending |
| EXIT-02 | Phase 2 | Pending |
| EXIT-03 | Phase 2 | Pending |
| EXIT-04 | Phase 2 | Pending |
| EXIT-05 | Phase 2 | Pending |
| EXIT-06 | Phase 2 | Pending |
| EXIT-07 | Phase 2 | Pending |
| EXIT-08 | Phase 2 | Pending |
| EXIT-09 | Phase 2 | Pending |
| PYRA-01 | Phase 2 | Pending |
| PYRA-02 | Phase 2 | Pending |
| PYRA-03 | Phase 2 | Pending |
| PYRA-04 | Phase 2 | Pending |
| PYRA-05 | Phase 2 | Pending |
| STATE-01 | Phase 3 | Pending |
| STATE-02 | Phase 3 | Pending |
| STATE-03 | Phase 3 | Pending |
| STATE-04 | Phase 3 | Pending |
| STATE-05 | Phase 3 | Pending |
| STATE-06 | Phase 3 | Pending |
| STATE-07 | Phase 3 | Pending |
| NOTF-01 | Phase 6 | Pending |
| NOTF-02 | Phase 6 | Pending |
| NOTF-03 | Phase 6 | Pending |
| NOTF-04 | Phase 6 | Pending |
| NOTF-05 | Phase 6 | Pending |
| NOTF-06 | Phase 6 | Pending |
| NOTF-07 | Phase 6 | Pending |
| NOTF-08 | Phase 6 | Pending |
| NOTF-09 | Phase 6 | Pending |
| NOTF-10 | Phase 8 | Pending |
| DASH-01 | Phase 5 | Pending |
| DASH-02 | Phase 5 | Pending |
| DASH-03 | Phase 5 | Pending |
| DASH-04 | Phase 5 | Pending |
| DASH-05 | Phase 5 | Pending |
| DASH-06 | Phase 5 | Pending |
| DASH-07 | Phase 5 | Pending |
| DASH-08 | Phase 5 | Pending |
| DASH-09 | Phase 5 | Pending |
| SCHED-01 | Phase 7 | Pending |
| SCHED-02 | Phase 7 | Pending |
| SCHED-03 | Phase 7 | Pending |
| SCHED-04 | Phase 7 | Pending |
| SCHED-05 | Phase 7 | Pending |
| SCHED-06 | Phase 7 | Pending |
| SCHED-07 | Phase 7 | Pending |
| CLI-01 | Phase 4 | Pending |
| CLI-02 | Phase 4 | Pending |
| CLI-03 | Phase 4 | Pending |
| CLI-04 | Phase 4 | Pending |
| CLI-05 | Phase 4 | Pending |
| ERR-01 | Phase 4 | Pending |
| ERR-02 | Phase 8 | Pending |
| ERR-03 | Phase 8 | Pending |
| ERR-04 | Phase 8 | Pending |
| ERR-05 | Phase 8 | Pending |
| ERR-06 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 78 total (DATA 6 + SIG 8 + SIZE 6 + EXIT 9 + PYRA 5 + STATE 7 + NOTF 10 + DASH 9 + SCHED 7 + CLI 5 + ERR 6)
- Mapped to phases: 78
- Unmapped: 0

**Per-phase counts:**
- Phase 1 (Signal Engine Core): 8 reqs
- Phase 2 (Sizing/Exits/Pyramiding): 20 reqs
- Phase 3 (State Persistence): 7 reqs
- Phase 4 (E2E Skeleton): 13 reqs
- Phase 5 (Dashboard): 9 reqs
- Phase 6 (Email Notification): 9 reqs
- Phase 7 (Scheduler + Deploy): 7 reqs
- Phase 8 (Hardening): 5 reqs
- **Total: 78**

---
*Requirements defined: 2026-04-20*
*Traceability populated: 2026-04-20 (roadmap creation)*
