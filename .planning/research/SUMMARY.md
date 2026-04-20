# Project Research Summary

**Project:** Trading Signals — SPI 200 & AUD/USD Mechanical System
**Domain:** Python mechanical trading signal generator (single-operator, daily-close, signal-only, email-delivered)
**Researched:** 2026-04-20
**Confidence:** HIGH on stack/features/architecture; MEDIUM-HIGH on pitfalls (some risk items regime-dependent)

## Executive Summary

This is a narrow-on-purpose single-operator tool: one mechanical system, two instruments (`^AXJO`, `AUDUSD=X`), one daily cadence, one email per weekday morning. The SPEC.md is already thorough and the stack is essentially pinned — `yfinance + pandas + numpy + requests + schedule + python-dotenv + pytz` plus Resend for email and Chart.js (CDN) for a static dashboard. Research agreed the spec's stack is correct with three opinionated adjustments: **hand-roll ATR(14)/ADX(20)/+DI/-DI in ~60 lines of NumPy** (do NOT add `pandas-ta` or TA-Lib), **use `requests` for Resend** (skip the Python SDK), and **pin `yfinance>=0.2.65`** to dodge the mid-2025 rate-limit regressions.

Architecture is hexagonal-lite at 5-file scale: pure functions in `signal_engine.py`, I/O adapters in `state_manager.py` / `notifier.py` / `dashboard.py`, and `main.py` as the thin orchestrator. The canonical workflow is a single `run_daily_check()` function with named steps that can be read top-to-bottom — no pipeline abstraction, no framework. State lives in a single `state.json` written atomically (tempfile + `os.replace`) with a `schema_version` field from day one. The signal engine is the only place the business math exists, it takes plain args and returns plain values, and every indicator and decision is driven by fixture-based golden-file tests — no live yfinance in CI.

The dominant risk category is **silently wrong signals**: yfinance returning empty or stale frames with no exception, Wilder smoothing implemented as SMA instead of `ewm(alpha=1/period, adjust=False)`, ADX warm-up garbage, LONG→FLAT not closing positions, LONG→SHORT flips only half-executing in one run, `max(1, int(...))` silently breaching the 1% risk budget on small accounts, and `--test` runs corrupting production state. **Deployment flip:** the spec lists Replit as primary and GitHub Actions as fallback — research recommends inverting this. Replit's own docs warn against relying on filesystem persistence on published apps, and the `schedule` loop dies under Autoscale. **GitHub Actions with a committed `state.json`, `permissions: contents: write`, and a `concurrency:` block is the safer, free, stateless-by-design primary.** Replit becomes the interactive dev environment, or the "paid Reserved VM + Object Storage" option for operators who want a persistent dashboard URL.

## Key Findings

### Recommended Stack

Keep the spec's seven production dependencies — no additions. Hand-roll the technical indicators rather than pulling in a TA library whose canonical upstream (`pandas-ta`) is flagged for archival by July 2026, and whose C-extension alternative (TA-Lib) adds Replit build friction for three indicators. `requests` handles Resend in ~10 lines (Resend's Python SDK is a thin wrapper; matches Marc's Carbon Bookkeeping pattern). Chart.js goes in via the **UMD build pinned to an exact version** — the ESM build in a classic `<script>` tag is a known blank-chart footgun.

**Core technologies:**
- **Python 3.11** — Replit + `actions/setup-python@v5` default; stable for TA libs that transitively matter.
- **pandas 2.2.x + numpy 1.26/2.x** — DataFrame math, rolling windows; pandas 2.2 supports both NumPy majors.
- **yfinance >=0.2.65, <0.3** — only free zero-auth source that covers `^AXJO` + `AUDUSD=X`. Pre-0.2.65 versions had 2025 rate-limit/session regressions.
- **requests >=2.32** — Resend HTTPS POST; already a yfinance transitive.
- **schedule >=1.2.2** — in-process daily tick for Replit path; GHA uses cron instead (no Python scheduler).
- **python-dotenv >=1.0.1** — local `.env` loading only (Replit Secrets / GHA secrets inject directly).
- **pytz >=2024.1** — `Australia/Perth` (UTC+8, no DST); spec-mandated, interchangeable with stdlib `zoneinfo`.
- **Chart.js 4.4.6 UMD (CDN, pinned)** — static dashboard equity curve.
- **pytest + pytest-freezer** — dev-only; fixture-driven indicator tests, frozen-clock scheduler tests.

**Adjustments to SPEC:**
- Pin yfinance to `>=0.2.65,<0.3` (tighter than spec's `>=0.2.40`).
- Pin Chart.js to an exact version (`4.4.6`) with explicit UMD path; no `@latest`.
- Treat GitHub Actions as primary deploy path (not fallback).

### Expected Features

Feature scope is already fully specified in SPEC.md — 13 active requirements all mapping to P1. Research added 3 small-but-essential items and identified 4 anti-features to hold the line on.

**Must have (table stakes — ship in v1):**
- Accurate daily signal (ATR/ADX Wilder, 2-of-3 momentum vote + ADX≥25 gate, FLAT→close semantics)
- Position sizing with vol-targeting (clip [0.3, 2.0]) and pyramiding (+1×/+2× ATR, max 3 contracts)
- Exit rules — signal reversal, ADX<20 dropout, trailing stop (3× LONG / 2× SHORT ATR from peak)
- `state.json` persistence — account, positions, signals, trade_log, equity_history, last_run
- Daily HTML email via Resend with ACTION REQUIRED block on signal change, mobile-responsive dark theme
- Weekday heartbeat email (unchanged-signal "no action" email every run so silence = broken app)
- Dashboard HTML with equity curve, positions, last 20 trades, key stats
- Scheduler: weekday 08:00 AWST (= 00:00 UTC cron `0 0 * * 1-5`)
- CLI: `--test`, `--reset`, `--force-email` with structural read-only guarantees
- Graceful error handling (never crash silently; surface errors in next email)
- **[ADD] `schema_version` field + atomic writes (tempfile + `os.replace`)** — cheap insurance against crash-mid-write data loss
- **[ADD] Stale-run banner when `last_run` > 2 days old** — operator's only signal that the scheduler died
- **[ADD] Weekday gate inside `run_daily_check`** even when using `schedule` — Always-On restarts can land on weekends

**Should have (v1.x polish after 4 weeks stable):**
- Timestamped state backups + `--restore` flag to pick one
- `--dry-run` flag (compute + print, no write, no email)
- Signal history panel and per-instrument ADX/Mom chart in dashboard
- CSV trade-log export (`--export-trades`) for tax time
- Slack webhook as secondary channel for action-required days

**Defer (v2+ — only with concrete trigger):**
- More instruments (each needs its own backtest + contract-spec block)
- Weekly-cadence mode switch (if daily results ever diverge from backtest)
- Richer dashboard charts

**Anti-features (resist permanently):**
- Live broker execution / order submission (hard constraint)
- Intraday / tick-level signals (different product)
- Multi-user / auth / SPA dashboard
- Database (SQLite/Postgres) — state.json fits for ~40 years
- News/sentiment/auto-tuning — breaks determinism and the backtested edge

### Architecture Approach

Hexagonal-lite at 5-file scale: pure functions separated from I/O, orchestrated by a thin `main.py`. All business logic lives in `signal_engine.py` as pure functions over `(df, args)` — the only I/O leak is `fetch_data` (kept here for DataFrame-contract cohesion). State is a plain dict throughout (JSON-serialisable trivially, no custom class). A single `run_daily_check()` function in `main.py` expresses the workflow as 12 named sequential steps — no pipeline abstraction, no middleware, no callbacks. Entry paths differ by deployment (Replit sits in `schedule` loop; GHA passes `--once` and exits) but both call the same `run_daily_check()`. Tests drive the pure core with committed OHLCV fixtures and golden indicator values — no live yfinance in CI.

**Major components:**
1. **`main.py`** — CLI parsing, dotenv, scheduler-vs-one-shot dispatch, orchestration, top-level error boundary. Owns time (passes `as_of_date` down). No math, no Resend inline, no state parsing.
2. **`signal_engine.py`** — Pure indicator math (ATR/ADX/Mom/RVol), signal vote, sizing, stop/pyramid math, unrealised P&L, plus the one `fetch_data` yfinance call. Deterministic, clock-free, stateless.
3. **`state_manager.py`** — Load/save `state.json` with atomic write, corruption recovery (backup + reinit), schema versioning & migrations, helpers (`record_trade`, `update_equity_history`, `reset_state`). No signal logic, no network.
4. **`notifier.py`** — Build subject + HTML body (inline CSS, mobile-safe), POST to Resend, degrade gracefully when `RESEND_API_KEY` missing. Writes `last_email.html` in test mode.
5. **`dashboard.py`** — Render `dashboard.html` from state + today's indicator snapshot. Write-only; never mutates state.
6. **`state.json`** — Single source of truth. Written atomically. Gitignored locally; committed by GHA after each run for durable state.
7. **`.github/workflows/daily.yml`** — Cron `0 0 * * 1-5` (weekday 00:00 UTC = 08:00 AWST), `setup-python@v5`, `stefanzweifel/git-auto-commit-action@v5` for `state.json` commit-back, `permissions: contents: write`, `concurrency: trading-signals`.

**Key separation rule:** every function in `signal_engine.py` takes plain arguments and returns plain values. `signal_engine ↔ state_manager` have **no direct link** — all interaction goes through `main.py`. This keeps tests untangled.

### Critical Pitfalls

Top pitfalls that cause silently-wrong output in a signal-only app (where silently wrong is worse than a crash because the operator places real money trades from it):

1. **yfinance silent partial/empty downloads** — `yf.download` returns empty frames or stale last-bars without raising. **Mitigate:** assert `len(df) >= 300`, assert `df.index[-1].date()` is recent per-instrument staleness budget, treat "empty after 3× retry" as hard fail (email error, do NOT write state, do NOT compute signal).
2. **Wilder ATR/ADX implemented as SMA instead of `ewm(alpha=1/period, adjust=False)`** — numbers look plausible but diverge materially from backtest; trailing stops hit too often. **Mitigate:** golden-file tests with hand-calculated 30-bar fixtures, 1e-9 tolerance via `numpy.testing.assert_allclose`; `min_periods=period` on every ewm call so leading bars are NaN, not garbage.
3. **LONG→FLAT doesn't close; LONG→SHORT one-run flip misses the SHORT** — ambiguous "signal reversal" semantics, and a single-pass exit-then-entry check that reads stale `position.active`. **Mitigate:** write the full 9-cell truth table test ({LONG,SHORT,none} × {LONG,SHORT,FLAT}); two-phase eval — apply exits first, then evaluate entries against the updated state.
4. **`max(1, int(n_contracts))` silently breaches 1% risk budget on small accounts** — one SPI contract can be 6× the intended risk at $100k account size. **Mitigate:** replace with `if n == 0: skip trade with warning`, OR keep the floor but surface effective risk loudly in every email. Log raw vs clipped values.
5. **Pyramiding double-adds on a gap-up day** — single `if unrealised >= 1×ATR: add` can fire twice in one run if price gaps to +2.3×ATR. **Mitigate:** gate on persisted `pyramid_level`, increment by 1 max per run, only evaluate the next-level threshold. State-machine test with gap-up fixture.
6. **state.json crash mid-write corrupts months of history** — default `open('w') + json.dump` isn't atomic. **Mitigate:** `tempfile.mkstemp` + `f.flush()` + `os.fsync()` + `os.replace(tmp, path)` pattern; keep rolling `state.json.bak`; add `schema_version` from day one.
7. **Replit Autoscale loses state; `schedule` dies on sleep** — `schedule` needs a long-running process, Replit Autoscale is stateless-by-design. **Mitigate:** **GitHub Actions is the primary path**, not the fallback. `cron: '0 0 * * 1-5'`, `permissions: contents: write`, `concurrency` block, `stefanzweifel/git-auto-commit-action@v5` for state persistence. Replit becomes optional (Reserved VM + Always On).
8. **`--test` flag writes state anyway** — if `save_state` isn't gated, test runs corrupt prod state (pyramid levels, equity history, last_run). **Mitigate:** structurally separate `compute_everything(state)` → `if not test: apply + save`. Assert `state.json` mtime unchanged after `--test` run.
9. **Timezone off-by-one** — `^AXJO` closes 06:00 UTC, `AUDUSD=X` rolls 21:00 UTC, Perth is UTC+8 no DST. Mixing these yields stale "today" labels. **Mitigate:** separate `signal_as_of = df.index[-1].date()` (from data) from `run_date = datetime.now(Australia/Perth)` (from clock); log both; never substitute. Email says "act at next session open", not "act now".
10. **Chart.js ESM served into classic `<script>` = blank chart** — `import` statement SyntaxError. **Mitigate:** explicit UMD path: `https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js` with SRI hash.

Full 20-pitfall list and recovery playbook in `.planning/research/PITFALLS.md`.

## Implications for Roadmap

**Reconciling the phase counts:** Architecture proposes 7 phases ordered by dependency; Pitfalls maps 20 pitfalls to 10 phase slots. The 10-slot model is finer-grained and better for risk-tracking; the 7-phase model is the shippable-increment model. **Recommendation: use 7 build-order milestones, each internally broken into phases where risk density warrants.** The signal engine milestone in particular may need 2–3 internal phases because it concentrates the highest-risk pitfalls (3, 4, 5, 6, 7, 10, 11, 12) and demands operator confirmation on ambiguous semantics before committing to code.

### Phase 1: Signal Engine Foundation (pure-math core)
**Rationale:** Signal correctness is the entire product. Build it first, in isolation, driven by fixture-based golden-file tests — before any network, state, or email code exists. Every downstream phase depends on stable indicator and signal contracts, and the highest-risk pitfalls (Wilder ATR/ADX, ADX warm-up garbage, RVol-near-zero blow-up, LONG→FLAT semantics, LONG→SHORT two-phase eval, pyramid state machine, trailing-stop intraday convention, contract multipliers) all live here.
**Delivers:** `signal_engine.py` with hand-rolled ATR(14)/ADX(20)/+DI/-DI/Mom/RVol, signal vote, position sizing, pyramid check, trailing-stop math, unrealised P&L. `tests/test_signal_engine.py` with committed CSV fixtures for both instruments and golden-file indicator outputs. Zero yfinance, zero Resend, zero file I/O outside tests.
**Addresses:** All P1 signal/sizing/exit/pyramid features from FEATURES.md.
**Avoids:** Pitfalls 3 (Wilder), 4 (ADX warm-up), 6 (FLAT closes), 7 (LONG→SHORT flip), 8 (RVol zero), 9 (risk-budget breach), 10 (pyramid double-add), 11 (close-only stops), 12 (multiplier errors), 20 (live-API tests).
**Operator confirmation required before build:** Trailing-stop convention (intraday high/low for peak and hit-check vs close-only) — impacts backtest reconciliation. `max(1, int(...))` floor policy — accept-with-warning or skip-trade.

### Phase 2: State Persistence with Recovery
**Rationale:** State is the second deterministic contract the rest of the app depends on. Can be built in parallel with Phase 1 (no shared code). Must ship before end-to-end wiring so the orchestrator has a reliable storage layer to call.
**Delivers:** `state_manager.py` with `load_state`, `save_state` (atomic via tempfile + `os.replace` + fsync), `_initial_state`, `_migrate_if_needed`, `_backup_corrupt_file`, `record_trade`, `update_equity_history`, `reset_state`. Schema invariants documented. `schema_version` field from day one.
**Uses:** Python stdlib `tempfile`, `os.replace`, `json`.
**Implements:** Persistence/Output layer from ARCHITECTURE.md.
**Avoids:** Pitfalls 13 (crash mid-write), 19 (test flag mutates state — structural separation of compute and persist enforced here).

### Phase 3: End-to-End Skeleton (fetch + wire, no email, no dashboard)
**Rationale:** First point where the app runs against live data. Shipping this early lets Marc verify the core behaviour daily-by-hand for ~1 week before outputs are layered on — if the signal logic is wrong, it surfaces before it gets buried under email formatting.
**Delivers:** `signal_engine.fetch_data` with 3× retry + shape assertions (non-empty, len>=300, last-bar-date staleness check). `main.py` orchestrator with `run_daily_check`, CLI parsing (`--test`, `--reset`, `--once`), dotenv loading, top-level error boundary, structured console logs. `python main.py --once` reads Yahoo, computes signals, updates state.json, prints summary.
**Uses:** yfinance pinned `>=0.2.65,<0.3`, `python-dotenv`, stdlib `argparse`.
**Avoids:** Pitfalls 1 (yfinance silent empty), 2 (AXJO/Perth off-by-one — log both `signal_as_of` and `run_date`), 5 (look-ahead — email copy says "act at next open").

### Phase 4: Dashboard (visual verification)
**Rationale:** Parallel-able with Phase 5 (no shared code). Visual verification before email work starts — Marc can eyeball state and P&L after each `--once` run.
**Delivers:** `dashboard.py` rendering `dashboard.html` with inline CSS, Chart.js 4.4.6 UMD from pinned CDN (with SRI hash), equity curve, positions table, last 20 trades, key stats (total return, Sharpe, max DD, win rate), AWST "Last updated" timestamp. No `<meta refresh>` hammering.
**Avoids:** Pitfalls 15 (meta-refresh), 16 (Chart.js CDN drift).

### Phase 5: Email Notification
**Rationale:** The one-user-facing output. Independent of dashboard. Must ship with robust graceful-degradation path (missing API key, 4xx/5xx, network error) so email failure never kills the workflow.
**Delivers:** `notifier.py` with `build_subject`, `build_email_html` (inline CSS, mobile-responsive, dark theme, ACTION REQUIRED red-border block on signal change, stale-run banner, warnings carry-over), `send_signal_email` POSTing to Resend with 15s timeout. `--force-email` flag. Test mode writes `last_email.html` instead of sending. Resend domain verification (SPF/DKIM/DMARC on `carbonbookkeeping.com.au`) confirmed before first live send.
**Avoids:** Pitfalls 14 (Resend deliverability — verify in Resend dashboard, not just API 200).

### Phase 6: Scheduler + Deployment (GitHub Actions primary)
**Rationale:** Lights-out operation. GHA-first because Replit's filesystem persistence is not guaranteed per their own docs and the `schedule` loop dies on Autoscale. Replit becomes optional/dev-only.
**Delivers:** `.github/workflows/daily.yml` with `cron: '0 0 * * 1-5'`, `permissions: contents: write`, `concurrency: { group: trading-signals, cancel-in-progress: false }`, `actions/checkout@v4`, `actions/setup-python@v5`, `stefanzweifel/git-auto-commit-action@v5` for state.json commit-back, manual `workflow_dispatch:` trigger. Scheduler loop in `main.main()` for Replit/local dev path with weekday gate in `run_daily_check`. `.env.example` finalised. Setup notes in `main.py` docstring.
**Avoids:** Pitfalls 17 (Replit Autoscale), 18 (GHA state.json race/perms/drift).
**Note:** The SPEC framing of "Replit primary, GHA fallback" should be **inverted** in the deployment guide. Both documented; GHA is the recommended default.

### Phase 7: Hardening + Long-Tail
**Rationale:** Absorb real-world failure modes observed over the first 1–2 weeks of live running. Formalise recovery paths.
**Delivers:** Warning carry-over from `state.warnings` into the next email header. Stale-state banner (>2 days). Schema migration path exercised with at least one no-op version bump. Crash-email path tested by deliberate fault injection. Timestamped backups + `--restore` flag. `--dry-run` flag. Optional `signals.log` rolled daily. Recovery runbook documented.
**Avoids:** Pitfalls 1 (warning carry-over surfaces data issues to operator), and closes the "looks done but isn't" checklist from PITFALLS.md.

### Phase Ordering Rationale

- **Phases 1 & 2 are the only true pre-requisites** — everything else is glue and adapters on top of a proven signal engine + proven state layer. Build both in parallel if capacity allows.
- **Phase 3 ships the first live behaviour** with no outputs except console logs, so buggy signals surface before email formatting or dashboard polish hides them.
- **Phases 4 & 5 are parallel-able** — dashboard and email share no code, only read the same state + report view-model.
- **Phase 6 is deliberately late** because scheduling without validated outputs is pointless; lights-out deployment goes in only after the one-shot path is trusted.
- **Phase 7 is explicitly post-shipping** — hardening against failure modes that only appear in production.

### Research Flags

**Phases likely needing deeper research during planning (`/gsd-research-phase`):**
- **Phase 1 (Signal Engine):** Risk-dense. Multiple ambiguous decisions need operator confirmation before code: trailing-stop intraday vs close-only convention; `max(1, int(...))` floor policy; LONG→FLAT close semantics; pyramid level state machine; per-instrument contract multiplier decision (full SPI $25/pt vs SPI mini $5/pt). Recommend a discuss-phase pass specifically to pin these with Marc before Phase 1 implementation.
- **Phase 6 (Deployment):** GHA permissions model, cron drift expectations, state.json commit-back race conditions, and the Replit vs GHA recommendation inversion all need explicit operator sign-off because they contradict the SPEC's primary/fallback ordering.

**Phases with standard patterns (skip phase research):**
- **Phase 2 (State Persistence):** Atomic-write pattern is stdlib-standard (`tempfile` + `os.replace`); JSON schema migration is well-trodden ground.
- **Phase 3 (E2E Skeleton):** Thin orchestrator + dotenv + argparse — bread-and-butter Python CLI pattern.
- **Phase 4 (Dashboard):** Static HTML + pinned Chart.js UMD via CDN is a fixed recipe once the pitfall items (pinning, SRI, removing `<meta refresh>`) are noted.
- **Phase 5 (Email):** `requests.post` to Resend is ~10 lines; HTML email mobile-responsive conventions are well-documented; Marc has working precedent from Carbon Bookkeeping.
- **Phase 7 (Hardening):** Reactive — driven by what Phase 3–6 surface in live running, not by upfront research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core libraries are industry-standard and spec-pinned; one opinionated call (hand-roll TA) is well-defended by the pandas-ta archival signal and the low line count involved. |
| Features | HIGH | SPEC.md is already thorough; scope is narrow-on-purpose; 13 P1 items map 1:1 with FEATURES.md table stakes. Anti-features are clearly bounded. |
| Architecture | HIGH | Hexagonal-lite at 5-file scale is the standard Python pattern for small scheduled jobs; every component boundary is defended by reference to SPEC + PITFALLS. |
| Pitfalls | MEDIUM-HIGH | 20 pitfalls identified; the logic-correctness ones (3, 6, 7, 10, 11) are HIGH confidence (directly from SPEC semantics); the data-quality ones (1, 2, 8) are MEDIUM because they depend on yfinance/Yahoo behaviour which varies. Recovery playbook is HIGH. |

**Overall confidence:** HIGH — the domain is narrow, SPEC is already detailed, every major architectural decision is defensible from first principles, and the main risk is logic correctness inside `signal_engine.py` which is the lightest-weight, fastest-iterating, fixture-testable part of the codebase.

### Gaps to Address

- **Trailing-stop convention** (intraday high/low update and intraday hit-check vs close-only): SPEC is silent on intraday. Pitfall 11 recommends intraday as the consistent choice for a daily-decision system; **needs operator confirmation in Phase 1 discuss step** — impacts backtest reconciliation directly.
- **`max(1, int(n_contracts))` floor policy:** Accept-with-warning (keep floor, surface effective risk loudly) or skip-trade (drop the floor, miss the trade). **Needs operator confirmation in Phase 1** — impacts P&L realism vs trade frequency.
- **Contract multiplier reality-check for SPI:** $25/pt (full ASX 200 futures) vs $5/pt (SPI mini) — operator's actual broker determines which is correct. **Confirm in Phase 1 constants dict.**
- **Replit vs GHA primary path:** SPEC says Replit-primary. Research says GHA-primary. **Needs operator sign-off in Phase 6** — both paths will be documented regardless, but the deployment guide should guide toward one.
- **Resend domain verification for `signals@carbonbookkeeping.com.au`:** MEMORY.md notes Resend is configured for Carbon Bookkeeping. **Verify this specific sender in Resend dashboard before Phase 5 first live send** — SPF/DKIM/DMARC CNAMEs must be present for deliverability.
- **yfinance version drift:** 2025 saw multiple breaking releases. Pin an exact version in Phase 3 requirements.txt (not `>=`) and bump deliberately. Re-verify the `>=0.2.65` choice at build time.
- **LONG→FLAT semantics** (whether FLAT (0) triggers a close): Phase 1 9-cell truth table will force a decision. Recommended: `if new_signal != current_direction and position.active: close` — FLAT closes.

## Sources

### Primary (HIGH confidence)
- `.planning/PROJECT.md` — project constraints, deployment targets, Perth AWST schedule
- `SPEC.md` — 513-line functional spec covering signal rules, email format, CLI flags, state schema, error handling
- `~/.claude/CLAUDE.md` — global patterns: atomic file writes, fire-and-forget async dangers, HTML escaping, async/await discipline
- `MEMORY.md` — Resend config status (Carbon Bookkeeping), Perth UTC+8, Digital Ocean precedent, Anthropic/Resend key rotation dates
- Resend API reference (resend.com/docs/api-reference/emails/send-email) — bearer auth, JSON body, 200/2xx semantics
- Chart.js v4 CDN discussion (github.com/chartjs/Chart.js/discussions/11219) — UMD vs ESM pitfall
- GitHub Actions workflow permissions docs — `permissions: contents: write` requirement
- Python stdlib — `tempfile.mkstemp` + `os.replace` atomic-write idiom (POSIX)
- Wilder, J. Welles — "New Concepts in Technical Trading Systems" (1978) — canonical ATR/ADX `alpha = 1/period`

### Secondary (MEDIUM confidence)
- yfinance issues #2567 (2025 rate-limit), #2496 (session breaking change) — informed `>=0.2.65` pin
- yfinance release notes — `auto_adjust` default flipped in 0.2.51
- Replit Reserved VM / Autoscale / Scheduled Deployments docs — filesystem persistence warning, scale-to-zero mismatch with schedulers
- GitHub Actions cron drift discussions — up to ~30 min delay, inactive-repo pause behaviour
- `stefanzweifel/git-auto-commit-action@v5` — standard pattern for state commit-back
- pandas-ta fork landscape (PyPI + GitHub forks) — informed hand-roll decision
- Leapcell blog: "Scheduling Tasks in Python: APScheduler vs Schedule" — confirmed `schedule` suitability for single-job daemons

### Tertiary (LOW confidence — validate during planning)
- Specific Replit Autoscale/Reserved VM pricing and feature set — Replit's product lineup shifts quarterly; re-verify in Phase 6
- Exact Resend SDK feature set at build time — re-verify before Phase 5 in case webhook/batch features arrive that change the "use requests" call
- Yahoo Finance `^AXJO` and `AUDUSD=X` symbol stability — informal/scraped, no SLA; first Phase 3 runs will confirm

---
*Research completed: 2026-04-20*
*Ready for roadmap: yes*
