# Milestones — Trading Signals

## v1.0 MVP — Mechanical Signal System

**Shipped:** 2026-04-24
**Timeline:** 4 days (2026-04-20 → 2026-04-24)

### Delivered

A daily-cadence Python CLI that fetches SPI 200 and AUD/USD from yfinance, computes ATR/ADX/momentum-vote signals, sizes positions with trailing stops + pyramiding, renders an HTML dashboard, emails operator via Resend at 08:00 AWST weekdays via GitHub Actions, and persists full state/trade history atomically with corruption recovery, configurable starting account + contract tiers, and crash-email boundaries.

### Stats

- **Phases:** 9 (8 original + 1 gap-closure)
- **Plans:** 33 (all complete)
- **Commits:** 250
- **Source:** ~5,800 LOC Python (8 modules + hex-lite architecture)
- **Tests:** 662 passing, 0 failing
- **Requirements:** 80/80 verified (DATA 6, SIG 8, SIZE 6, EXIT 9, PYRA 5, STATE 7, NOTF 10, DASH 9, SCHED 7, CLI 5, ERR 6, CONF 2)

### Key Accomplishments

1. **Deterministic indicator library** — pure-math ATR(14), ADX(20), +DI, -DI, Mom, RVol with hand-rolled Wilder smoothing, golden-file tested to 1e-9 tolerance on 400-bar canonical fixtures (Phase 1).
2. **Full trading lifecycle** — position sizing (skip-if-zero, no `max(1,…)` floor), ADX-gated entry, trailing-stop exits (intraday H/L), and pyramid state machine with 9-cell signal-transition coverage (Phase 2).
3. **Durable state** — atomic `state_manager.py` with tempfile+fsync+os.replace writes, `_migrate` chain handling v1→v2 schema, JSONDecodeError → backup + reinit recovery, and single-writer invariant for warnings (Phase 3).
4. **End-to-end orchestrator** — `main.py` wires yfinance fetch → signal → size → dashboard → email with typed-exception ladder, CLI flags (`--once`, `--reset`, `--test`), and structured logging by `[Signal]/[State]/[Email]/[Sched]/[Fetch]` prefixes (Phase 4).
5. **Production-grade dashboard + email** — static HTML dashboard with Chart.js 4.4.6 UMD SRI-pinned equity curve, mobile-responsive dark-themed email template, Resend HTTPS dispatch with retry, last_email.html fallback (Phases 5-6).
6. **Deployed and scheduled** — GitHub Actions cron `0 0 * * 1-5` (08:00 AWST) with state commit-back; Replit alternative documented (Phase 7, operator-verified).
7. **Hardening against real-world failure modes** — warning carry-over banner, stale-state red banner, corrupt-state recovery notification, unhandled-exception crash email via Layer-B boundary, configurable `--initial-account`/`--spi-contract`/`--audusd-contract` with interactive Q&A, preview, and non-TTY guard (Phase 8, 17 locked design decisions).
8. **Milestone gap closure** — ERR-01 spec reconciled with locked no-email-on-data-error design, REQUIREMENTS.md traceability 80/80 sync, GHA `timeout-minutes: 10` runaway-run cap (Phase 9).

### Architecture

Hexagonal-lite. Pure-math modules (`signal_engine`, `sizing_engine`, `system_params`) with AST-enforced forbidden-imports blocklist. I/O adapters (`state_manager`, `notifier`, `dashboard`) with no cross-imports. `main.py` is the sole orchestrator. All invariants tested by `TestDeterminism::test_forbidden_imports_absent`.

### Known Deferred Items

Operator-facing UAT scenarios that require real-world verification (see `STATE.md` §Deferred Items, 4 items):
- Phase 5 dashboard visual check
- Phase 6 email rendering on real Gmail
- Phase 6 HUMAN-UAT (3 scenarios)
- 1 quick-task cleanup

Plus accepted tech debt deferred to v2:
- F1 full-chain integration test harness
- `_LAST_LOADED_STATE` thread-safety (single-threaded today; revisit if parallel runs appear)
- Phase 8 holiday-staleness 2-day threshold (may false-trigger on Mon-holiday Tuesdays)
- 19 pre-existing ruff F401 warnings in notifier.py
- Phase 7 carry-overs: IN-02 README badge placeholder, IN-03 TestWeekdayGate fake

### Audit

See [`v1.0-MILESTONE-AUDIT.md`](milestones/v1.0-MILESTONE-AUDIT.md) for the re-audit that flipped `tech_debt` → `passed` after Phase 9.

### Retrospective

See [`RETROSPECTIVE.md`](RETROSPECTIVE.md) for what worked, what was inefficient, and lessons for v2.

---

## v1.1 Interactive Trading Workstation

**Shipped:** 2026-04-30
**Timeline:** 6 days (2026-04-25 → 2026-04-30)
**Tag:** `v1.1`

### Delivered

The v1.0 email-only CLI lifted into a hosted, interactive trade journal at `https://signals.mwiriadi.me`. FastAPI + uvicorn + nginx + Let's Encrypt on a DigitalOcean droplet. systemd manages the daily 08:00 cycle (replaces GHA cron). Cookie session + TOTP 2FA + 30-day trusted-device cookies + magic-link recovery (Phase 16.1). HTMX forms record executed trades; live calculator surfaces stop-loss + pyramid thresholds; drift sentinels flag position-vs-signal divergence in both email banner and dashboard row in lockstep. F1 full-chain integration test (boundary-only mocks, sabotage-verified).

### Stats

- **Phases:** 8 (10, 11, 12, 13, 14, 15, 16, 16.1)
- **Plans:** 38 (all complete)
- **Commits:** 179
- **Files modified:** 166 (+57,623 / −264 LOC)
- **Tests at close:** 1319 passing / 12 deferred (pre-existing nginx config + ruff binary env issues)
- **Requirements:** 40/40 verified (see [v1.1-REQUIREMENTS.md](milestones/v1.1-REQUIREMENTS.md))

### Key Accomplishments

1. Hosted dashboard live — `https://signals.mwiriadi.me/` HTTPS + HSTS + Let's Encrypt cert + auth gate
2. Trade journal mutations — HTMX forms preserve sole-writer invariant on `state_manager.save_state()`
3. Phone-friendly auth UX (Phase 16.1) — cookie session + TOTP enroll/verify + trusted-device opt-in + magic-link recovery
4. Drift sentinel pipeline — D-12 lockstep parity between email and dashboard banners; `[!]` subject prefix on critical events
5. F1 full-chain integration test — boundary-only mocks, sabotage-test verified
6. Operator UAT closure — UAT-16-A/B/C all verified through real-world deployment

### Notable Mid-Milestone Fix

Silent regression in `main.py::_run_daily_check_caught` (commit `3279c312`, 2026-04-23) discarded the 4-tuple from `run_daily_check(args)` and stopped the production droplet daemon from sending daily emails for ~7 days. Fixed in commit `879730d` with 4 regression tests + inverted Phase-4 fossil test. Captured as global learning.

### Known Deferred Items (carried into v1.2)

- 9 operator-driven UAT scenarios across Phases 13/14/16.1 (live-deployment hands-on)
- Phase 13 `13-VERIFICATION.md` human_needed items (droplet/curl)

Phase artifacts retained in `.planning/phases/` (not archived to milestones at v1.1 close).

### Archive

See [`milestones/v1.1-ROADMAP.md`](milestones/v1.1-ROADMAP.md) for full phase + decision details.

---

## v1.2 Trader-Grade Transparency & Validation

**Shipped:** 2026-05-10
**Timeline:** 11 days (2026-04-30 → 2026-05-10)
**Tag:** `v1.2`

### Delivered

Lifted the v1.1 hosted dashboard from "tells you what to do" → "shows you exactly why and tracks how it played out". Per-signal Inputs/Indicators/Vote panels make every signal reproducible by hand. Paper-trade ledger tracks open positions with mark-to-market P&L and aggregate stats. Stop-loss alerts dedup'd per state transition. `STRATEGY_VERSION` constant tags every signal/trade row so historical state stays interpretable across logic changes. 5-year walk-forward backtest gates strategy changes (`>100%` cumulative-return pass criterion), `/backtest` route renders report. UI overhaul converts decorative market dropdown into true two-axis market × function navigation with cookie + URL persistence. Code-quality sweep: Decimal money math, file-size hygiene (notifier/main/dashboard each <500 LOC), naive-datetime fail-closed, schema-migration contiguity assert, HTML-escape audit, API-key redaction, look-ahead-bias backtest test.

### Stats

- **Phases:** 9 (17, 19, 20, 22, 23, 24, 25, 26, 27 — Phase 18 multi-user + Phase 21 news deferred to v1.3+)
- **Plans:** 48 per-phase / 45 STATE.md count
- **Commits:** 221
- **Files changed:** 313 (+76,605 / −6,653)
- **Tests at close:** 1880+ passing (12 pre-existing failures carried from v1.1)
- **Requirements:** 22/22 verified (TRACE 5, LEDGER 6, ALERT 4, VERSION 3, BACKTEST 4) — see [v1.2-REQUIREMENTS.md](milestones/v1.2-REQUIREMENTS.md)
- **Git range:** `3ef2431..ad7f2a1`

### Key Accomplishments

1. **Per-signal calculation transparency** (Phase 17) — Inputs/Indicators/Vote panels with cookie allowlist toggle; STATE_SCHEMA_VERSION 4→5 with `ohlc_window` + `indicator_scalars`.
2. **Paper-trade ledger** (Phase 19) — manual entry, open/closed tables, mark-to-market unrealised P&L, aggregate stats; atomic-write contract preserved.
3. **Stop-loss monitoring & alerts** (Phase 20) — CLEAR/APPROACHING/HIT state machine, `[!stop]`-prefixed Resend alerts dedup'd via `last_alert_state`.
4. **Strategy versioning** (Phase 22) — `STRATEGY_VERSION='v1.2.0'` constant, signal/trade row stamping, v1.1.0 retroactive migration.
5. **5-year backtest validation gate** (Phase 23) — pure-compute `backtest/` module (hex-boundary respected), `/backtest` route + CLI + JSON history per `strategy_version`. Nyquist-validated.
6. **Dashboard UI/UX overhaul** (Phase 25) — true two-axis nav (`/markets/{m}/{fn}`), WAI-ARIA roving tabindex, status strip with countdown, first-run empty-state collapse, mobile font ≥16px, fieldset grouping, accessibility hardening; 22/22 design decisions verified. Schema v7→v8.
7. **Phase 25 follow-up** (Phase 26) — fixed 4 BROKEN regressions (multi-tab scoping non-functional, template placeholder leak → 401s, header session widget, deploy tests); zero `{{TEMPLATE}}` leaks in served HTML.
8. **Code-quality correctness sweep** (Phase 27) — Decimal money math (schema v8→v9 quantize-on-save), HTTP_TIMEOUT_S=30 standardized, API-key redaction, instrument regex tightening, `_assert_tz_aware` fail-closed, migration-chain contiguity fail-fast, `--version` flag, lazy yfinance import, signal-shape unification, look-ahead-bias backtest test, crash-email fallback. File splits: notifier.py 1974→package, main.py 1996→shim+modules, dashboard.py 2221→dashboard_legacy/ package (HTML output byte-identical). Nyquist-validated, security-verified.

### Architecture Additions

- New `backtest/` module (pure compute, hex-boundary respected, AST guard extended).
- `state.json` schema v4→v5 (`ohlc_window`+`indicator_scalars`) → v5→v6 (paper_trades) → v6→v7 (alert state) → v7→v8 (multi-tab market preferences) → v8→v9 (Decimal AUD-quantized money). Migration chain contiguity asserted at module load.
- `/markets/{MARKET}/{FN}` route family with cookie + URL persistence.
- `notifier/`, `dashboard_legacy/` packages (each module <500 LOC, public API preserved).
- DigitalOcean droplet + systemd documented as PRIMARY deploy path; GHA cron disabled (`.github/workflows/daily.yml.disabled`) preserved as rollback insurance only.

### Known Deferred Items (carried into v1.3 as Phase 28 backlog)

8 operator-facing UAT scenarios:

- Phase 17: ATR(14) hand-recalc to 1e-6, iOS Safari tap-to-toggle, cookie persistence across reload
- Phase 23: Live CLI yfinance run (`python -m backtest --years 5`), `/backtest` browser visual smoke
- Phase 26: Cold-start smoke test on production droplet (UAT-1), multi-tab market scoping browser walkthrough (UAT-2..6)

Plus accepted tech debt:

- `.planning/backtests` path is CWD-relative — fragile if CLI invoked outside project root
- Phases 17, 19, 20, 22, 24, 25, 26 lack formal Nyquist `VALIDATION.md` (only 23 + 27 have one)
- Phases 17, 19, 20, 22, 23, 24, 25, 26 lack dedicated `SECURITY.md` (only 27 has one) — inherit v1.1 perimeter
- 12 pre-existing test failures (test_nginx_signals_conf x9, test_notifier x2, test_setup_https_doc x1) carried from v1.1
- 5 ad-hoc post-ship polish commits 2026-05-08..2026-05-10 (scheduler tz fix, signal status ladder, v1.1 backtested per-market defaults, trace vote_params, market tab strip refresh) accepted into v1.2 but never phase-tracked. Decide in v1.3 whether to retroactively wrap as v1.2.1 patch phase.

### v1.2.1 — Retroactive Patch Wrap (2026-05-10)

Five ad-hoc post-ship polish commits (2026-05-08..05-10) formalised as a single retroactive patch phase per Phase 29 D-11/D-13. Behaviour-locking regression tests added in Phase 29 plan 29-03 where the commit changed observable behaviour; UX-only and existing-fixture-covered commits get pointer rows.

| Commit | Behaviour | Test | Note |
|--------|-----------|------|------|
| `05a4c0c` | Daily run fires at 08:00 Sydney (AEST/AEDT, DST-aware) | `tests/test_scheduler.py::TestSchedulerTimezone` | DST transition case included |
| `da31412` | Signal Status card renders trigger ladder + trailing-stop line | `tests/test_signals_status_ladder.py` | New regression suite |
| `b7ed1f2` | v11 backtested per-market defaults, $10K baseline, contract+financing UI | `tests/test_backtest_*` (existing fixture suite) | Pointer only — covered by deterministic backtest fixtures |
| `587b6f0` + `bb780af` | Trace panel renders engine-resolved vote params; backfill at render time for stale state rows | `tests/test_trace_vote_params.py` | Locality discipline per project LEARNING 2026-05-10 |
| `878199c` | Market tab strip refresh on tab click (active underline tracks selection) | none — UX | Visual-only fix, no behaviour contract |

### Audit

See [`milestones/v1.2-MILESTONE-AUDIT.md`](milestones/v1.2-MILESTONE-AUDIT.md) for the re-audit (status: `tech_debt` — no requirement gaps; one procedural gap on Phase 26 closed by `ad7f2a1`).

### Archive

See [`milestones/v1.2-ROADMAP.md`](milestones/v1.2-ROADMAP.md) for full phase + decision details. Phase dirs archived under [`milestones/v1.2-phases/`](milestones/v1.2-phases/).

---
