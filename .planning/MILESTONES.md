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
