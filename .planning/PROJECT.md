# Trading Signals — SPI 200 & AUD/USD Mechanical System

## What This Is

A **shipped** Python CLI (v1.0, 2026-04-24) that runs a mechanical trend-following trading system for two instruments — SPI 200 (`^AXJO`) and AUD/USD (`AUDUSD=X`) — via GitHub Actions cron at 08:00 AWST weekdays. It fetches daily OHLCV data, computes ATR/ADX/momentum-vote signals, sizes positions with trailing-stop + pyramiding, persists state atomically with corruption recovery, renders an HTML dashboard, emails the operator via Resend, and handles crashes with a last-ditch crash-email boundary. **Signal-only** — it never places live trades; it tells the operator what the system says they should be doing and tracks hypothetical P&L against a configurable starting account (default $100k).

**v1.1 direction (in progress):** Transform the email-only system into a hosted, interactive trade journal on DO. FastAPI + nginx serves `signals.yourdomain.com`; operator records executed trades via form; dashboard surfaces live stop-loss + pyramid thresholds and flags position-vs-signal drift.

## Current Milestone: v1.1 Interactive Trading Workstation

**Goal:** Transform the v1.0 email-only signal system into a hosted, interactive trade journal — a single URL viewable from any device, POST-able for recording executed trades, with live stop-loss + pyramid guidance.

**Target features:**
- Hosted dashboard at `signals.yourdomain.com` (FastAPI + nginx + Let's Encrypt on DO)
- Interactive trade journal: form-based open/close/modify via POST endpoints
- Live stop-loss + pyramid calculator surfaced per-instrument
- Sanity-check sentinels (position-vs-signal drift warnings)
- BUG-001 fix: `reset_state()` syncs `account` with `initial_account`
- Selected v1.0 tech debt: F1 full-chain integration test, ruff F401 cleanup, Phase 6 HUMAN-UAT completion

**Architecture (locked):** DO droplet = runtime (systemd: schedule loop + FastAPI web). GitHub = source + state history via deploy key push-back. HTMX or vanilla JS (no React). Shared-secret header auth.

**Prerequisites:** Domain purchased and pointing at droplet IP; Resend domain verification.

## Core Value

Deliver an accurate, reproducible daily signal and actionable instruction ("close LONG / open SHORT / hold") to one email inbox every weekday at 08:00 AWST — with full state persistence so P&L, positions, and trade history survive restarts. **Validated in v1.0.**

## Requirements

### Validated

All 80 v1 requirements verified in v1.0 (see [milestones/v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md)):

- ✓ **DATA (6)** — yfinance fetch, 400-day window, 3x retry, stale-data detection — v1.0
- ✓ **SIG (8)** — ATR(14), ADX(20), +DI, -DI, Mom1/3/12, RVol(20), 2-of-3 vote gated by ADX≥25 — v1.0
- ✓ **SIZE (6)** — vol-targeted sizing (1% LONG / 0.5% SHORT), skip-if-zero (no `max(1,…)` floor) — v1.0
- ✓ **EXIT (9)** — signal reversal, ADX<20 drop-out, trailing-stop hit (intraday H/L), 9-cell transition matrix — v1.0
- ✓ **PYRA (5)** — pyramid up to 3 contracts at +1×ATR and +2×ATR thresholds, gap-day capped — v1.0
- ✓ **STATE (7)** — atomic tempfile+fsync+os.replace writes, `_migrate` chain, corruption recovery — v1.0
- ✓ **NOTF (10)** — Resend HTML email, two-tier banner (critical vs routine), subject `[!]` prefix, warning carry-over, always-write last_email.html — v1.0
- ✓ **DASH (9)** — static dashboard.html with Chart.js 4.4.6 UMD SRI-pinned equity curve, positions, trades, key stats — v1.0
- ✓ **SCHED (7)** — GHA cron `0 0 * * 1-5`, UTC-assertion, `_run_schedule_loop`, `timeout-minutes: 10` cap — v1.0
- ✓ **CLI (5)** — `--once`, `--reset`, `--test`, `--force-email`, `--initial-account`, `--spi-contract`, `--audusd-contract` — v1.0
- ✓ **ERR (6)** — per-job never-crash (Layer A), outer crash-email boundary (Layer B), corrupt-state recovery, stale-state banner, Resend 5xx logged + warning-tracked, structured console logs — v1.0 (ERR-01 spec reconciled Phase 9: data-fetch errors log + exit rc=2, no email)
- ✓ **CONF (2)** — `--initial-account` float with `math.isfinite` guard, per-instrument contract tiers (`spi-mini/spi-standard/spi-full` × `audusd-standard/audusd-mini`), `_resolved_contracts` runtime materialisation — v1.0

### Active (v1.1+ candidates)

None committed. Candidates from v1.0 deferred tech debt:

- [ ] F1 full-chain integration test harness (single test exercising fetch → signals → sizing → dashboard → email unmocked)
- [ ] Holiday-calendar-aware staleness threshold (avoid false-positive red banner after Mon-holiday Tuesdays)
- [ ] Thread-safe `_LAST_LOADED_STATE` cache (only matters if parallel-run features appear)
- [ ] ruff F401 cleanup in notifier.py (19 pre-existing warnings)
- [ ] Phase 7 IN-02 README badge `${{GITHUB_REPOSITORY}}` literal placeholder fix (forker-only)
- [ ] Phase 7 IN-03 TestWeekdayGate fake returning None (test-quality polish)
- [ ] Phase 6 HUMAN-UAT completion (3 operator scenarios — email-rendering visual checks)
- [ ] Phase 5 + Phase 6 VERIFICATION.md human_needed items (dashboard + email real-world visual verification)

### Out of Scope (v1.0 validated)

- Live order execution — signal-only; Marc places trades manually. **Hard constraint.**
- Any instruments beyond SPI 200 and AUD/USD — adding more is a v2+ milestone.
- Intraday data / tick-level signals — daily close only.
- Backtesting UI — the app only runs forward.
- Multi-user accounts / auth — single-operator tool.
- React / Vue / any SPA framework — dashboard is a single static HTML file.
- Database — all state lives in one `state.json` file.
- Financial advice / regulatory disclosures — footer disclaimer only.

## Context

- **Shipped:** v1.0 on 2026-04-24 after 4 days of work (~5,800 source LOC Python, 662 tests, 250 commits, 9 phases).
- **User:** Marc (Perth, AWST UTC+8 year-round, no DST) — runs Carbon Bookkeeping, Resend configured with verified sender `signals@carbonbookkeeping.com.au`.
- **Architecture:** Hexagonal-lite. Pure-math modules (`signal_engine`, `sizing_engine`, `system_params`) with AST-enforced forbidden-imports blocklist. I/O adapters (`state_manager`, `notifier`, `dashboard`) with no cross-imports. `main.py` is the sole orchestrator.
- **Deployment:** DigitalOcean droplet systemd is the PRIMARY path (Phase 11 onwards). GitHub Actions cron is disabled (`.github/workflows/daily.yml.disabled`) per Phase 10 INFRA-03 to avoid duplicate signal emails; the disabled workflow retains `timeout-minutes: 10` as rollback insurance. Replit Always On remains documented as an alternative (see `docs/DEPLOY.md` — stale, rewrite deferred to post-Phase-12 docs-sweep per 10-CONTEXT.md Deferred Ideas).
- **State persistence:** The droplet's daily run commits `state.json` back to `origin/main` via a GitHub deploy key (Phase 10 INFRA-02 / `_push_state_to_git` in `main.py`); Replit filesystem persists if Always On is active.
- **Testing:** 662 tests passing, 0 failing. `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` AST-walks hex modules to enforce boundary invariants.
- **Known deferred UAT:** 4 operator-facing visual checks (dashboard rendering, Gmail email rendering) recorded in STATE.md §Deferred Items — cannot be automated in GSD session.

## Constraints

- **Tech stack**: Python 3.11.8, `yfinance 1.2.0`, `pandas 2.3.3`, `numpy 2.0.2`, `requests`, `schedule`, `python-dotenv`, `pytz`, `pytest 8.3.3`, `pytest-freezer`, `ruff 0.6.9` — all version-pinned in `requirements.txt`.
- **Email transport**: Resend HTTPS API only. No SMTP.
- **Storage**: Single `state.json` file. No SQLite/Postgres/Redis.
- **Dashboard**: Single self-contained `dashboard.html` with inline CSS and CDN Chart.js 4.4.6 (SRI-pinned). No build step.
- **Email rendering**: Inline CSS only — email clients strip `<style>` blocks. Must render on mobile.
- **Determinism**: Daily signal output reproducible from `state.json` + Yahoo data for the same date.
- **Signal-only**: No hook or flag places a live trade. Hard constraint.
- **Secrets**: All credentials via `.env` locally or GitHub Secrets — never committed. `state.json` is gitignored locally, committed only by the GHA workflow.
- **Schedule**: 08:00 Perth time weekdays — `cron "0 0 * * 1-5"` UTC.
- **Error budget**: App must never crash silently. All errors caught, logged, and surfaced in the next email as a warning (except `DataFetchError`/`ShortFrameError` which log + exit rc=2 — deliberate, per ERR-01 Phase 9 amendment).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python + yfinance + Resend | User already on Resend; Python has mature TA libs; runs on Replit/GHA with no infra | ✓ Good |
| Single `state.json` file | Simplicity, portability across Replit and GitHub Actions | ✓ Good |
| Perth time (AWST) schedule, cron `0 0 * * 1-5` UTC | Marc is in Perth — no DST simplifies cron | ✓ Good |
| ATR + vol-target sizing, `n_contracts == 0` skips trade (no floor) | Matches the backtested system exactly; 0-floor silently breaches risk budget on small accounts | ✓ Good |
| Static `dashboard.html` with Chart.js CDN (SRI-pinned) | Zero build step, matches prior backtest aesthetic; SRI prevents CDN tampering | ✓ Good |
| Signal-only, no live trading | Explicit user directive — risk mitigation | ✓ Good |
| DO droplet systemd PRIMARY (v1.1); GHA cron disabled, Replit alternative | Droplet gives HTTP-serving capability for FastAPI (v1.1 Phase 11+); GHA cron retired in Phase 10 INFRA-03 to avoid duplicate emails; state.json pushed back via deploy key per Phase 10 INFRA-02 | ✓ Good (v1.1) |
| Hexagonal-lite: signal_engine ↔ state_manager no cross-import; main sole orchestrator | Keeps pure-math modules testable in isolation; AST blocklist enforces at CI time | ✓ Good |
| Two-tier email banner (critical vs routine) + `[!]` subject prefix | Critical banners (stale-state, corrupt-recovery) always visible at top; routine warnings compact | ✓ Good (Phase 8) |
| `_LAST_LOADED_STATE` module cache for crash-email state summary | Gives crash email access to last-loaded state without threading state through the scheduler | ⚠️ Revisit if parallel runs appear (v2) |
| Underscore-prefix persistence rule (`_resolved_contracts`, `_stale_info`) | Runtime-only keys auto-stripped by `save_state`; new convention | ✓ Good (Phase 8 D-14) |
| ERR-01 data-fetch errors log + exit rc=2, no email | Transient yfinance/network errors are expected; emailing on every blip is noise | ✓ Good (Phase 9 spec amendment) |
| Trailing stops use intraday HIGH/LOW (peak updates + hit detection) | Consistent intraday convention matches how the backtest was built | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each milestone** (via `/gsd-complete-milestone`):
1. Validated section: shipped requirements marked with v version reference
2. Active section: new candidates for next milestone
3. Out of Scope audit: reasons still valid?
4. Context: LOC, tech stack, user feedback themes, known issues
5. Key Decisions: outcomes updated (✓ Good, ⚠️ Revisit, — Pending)

---

*Last updated: 2026-04-24 after v1.0 milestone shipped*
