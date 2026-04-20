# Trading Signals — SPI 200 & AUD/USD Mechanical System

## What This Is

A Python application that runs a mechanical trend-following trading system for two instruments — SPI 200 (`^AXJO`) and AUD/USD (`AUDUSD=X`) — by fetching daily OHLCV data, computing signals, persisting state, rendering a dashboard, and emailing a daily report every weekday morning Perth time. It is a **signal-only** tool for one user (Marc) — it never places live trades, it tells the operator what the system says they should be doing and tracks hypothetical P&L against a $100,000 starting account.

## Core Value

Deliver an accurate, reproducible daily signal and actionable instruction ("close LONG / open SHORT / hold") to one email inbox every weekday at 08:00 AWST — with full state persistence so P&L, positions, and trade history survive restarts.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Fetch daily OHLCV for `^AXJO` and `AUDUSD=X` via yfinance (400-day window, retry 3x on failure)
- [ ] Compute indicators on daily close: ATR(14) Wilder, ADX(20) Wilder with +DI/-DI, Mom1/Mom3/Mom12, RVol(20) annualised
- [ ] Generate signal using 2-of-3 multi-timeframe momentum vote gated by ADX>=25 (LONG / SHORT / FLAT)
- [ ] Size positions with ATR-based stop and vol-targeting (risk 1.0% LONG / 0.5% SHORT, trail 3.0x/2.0x ATR)
- [ ] Honour contract specs: SPI $25/point $30 cost round-trip; AUD/USD $10,000 notional $5 cost round-trip
- [ ] Apply exit rules daily: signal reversal, ADX<20 drop-out, trailing stop hit
- [ ] Pyramid up to 3 contracts at +1×ATR and +2×ATR unrealised profit thresholds
- [ ] Persist state to `state.json` with account, positions, signals, trade log, equity history
- [ ] Send daily HTML email via Resend with signal status, positions, P&L, and ACTION REQUIRED block on signal change
- [ ] Generate `dashboard.html` each run with Chart.js equity curve, open positions, last 20 trades, key stats
- [ ] Run on a daily schedule (08:00 AWST / 00:00 UTC) on weekdays
- [ ] Support `--test`, `--reset`, and `--force-email` CLI flags
- [ ] Handle Yahoo Finance failures, Resend failures, and corrupted state.json gracefully
- [ ] Emit structured console logs that are readable in Replit/GitHub Actions output

### Out of Scope

- Live order execution — this is signal-only; Marc places trades manually
- Any instruments beyond SPI 200 and AUD/USD — adding more is a future milestone
- Intraday data / tick-level signals — daily close only
- Backtesting UI — the app only runs forward; backtests were done separately
- Multi-user accounts / auth — single-operator tool, Resend API key and Replit Secrets are the only gate
- React / Vue / any SPA framework — dashboard is a single static HTML file
- Database — all state lives in one `state.json` file
- Financial advice / regulatory disclosures — footer disclaimer only

## Context

- **User:** Marc (Perth, AWST UTC+8 year-round, no DST) — runs Carbon Bookkeeping, already has Resend configured with verified sender `signals@carbonbookkeeping.com.au`.
- **Prior work:** Backtests with the same dark aesthetic (Chart.js, `#0f1117` background, green LONG / red SHORT / gold FLAT palette) already exist — the dashboard must match.
- **Deployment target:** Replit (with Always On) as primary; GitHub Actions with cron `0 22 * * 1-5` (8am AEST approximation — spec note: use `0 0 * * 1-5` for Perth 8am AWST) as the free fallback. Both are in scope for the docs/deployment guide.
- **State persistence:** Replit filesystem persists between runs when Always On is active; in GitHub Actions mode, the workflow commits `state.json` back to the repo.
- **Schedule window:** Scheduler fires once daily at 08:00 AWST; immediate first-run on process start for verification.
- **Timezones matter:** Spec mentions both AEST (22:00 UTC → 8am AEST) and AWST (00:00 UTC → 8am AWST). Marc is in Perth — schedule on `00:00` UTC. Dates/times in email/dashboard/console use AWST via pytz `Australia/Perth`.

## Constraints

- **Tech stack**: Python 3.11+, `yfinance`, `pandas`, `numpy`, `requests`, `schedule`, `python-dotenv`, `pytz` — no other frameworks, no Flask/Django/FastAPI.
- **Email transport**: Resend HTTPS API only (already configured for Carbon Bookkeeping). No SMTP/Nodemailer.
- **Storage**: Single `state.json` file. No SQLite/Postgres/Redis.
- **Dashboard**: One self-contained `dashboard.html` with inline CSS and CDN Chart.js. No build step.
- **Email rendering**: Inline CSS only — email clients strip `<style>` blocks. Must render on mobile.
- **Determinism**: Daily signal output must be reproducible from `state.json` + Yahoo data for the same date.
- **Signal-only**: Never expose any hook or flag that would place a live trade. Hard constraint.
- **Secrets**: All credentials via `.env` locally or Replit Secrets — never committed. `state.json` is gitignored locally, committed only by GitHub Actions workflow when running in that mode.
- **Schedule**: 08:00 Perth time weekdays — `schedule.every().day.at("00:00")` UTC is the canonical line.
- **Error budget**: App must never crash silently. All errors caught, logged, and surfaced in the next email as a warning.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python + yfinance + Resend | User already on Resend; Python has mature TA libs; runs on Replit/GHA with no infra | — Pending |
| Single `state.json` file | Simplicity, portability across Replit and GitHub Actions | — Pending |
| Perth time (AWST) schedule | Marc is in Perth — no DST simplifies cron | — Pending |
| ATR + vol-target sizing | Matches the backtested system exactly | — Pending |
| Static `dashboard.html` with Chart.js CDN | Zero build step, matches prior backtest aesthetic | — Pending |
| Signal-only, no live trading | Explicit user directive — risk mitigation | — Pending |
| Deployment: Replit primary, GitHub Actions fallback | Replit needs paid plan for Always On; GHA free alternative via cron | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-20 after initialization*
