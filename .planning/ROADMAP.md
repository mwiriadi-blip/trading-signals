# Roadmap: Trading Signals — SPI 200 & AUD/USD Mechanical System

## Milestones

- ✅ **v1.0 MVP — Mechanical Signal System** — Phases 1-9 (shipped 2026-04-24)

## Phases

<details>
<summary>✅ v1.0 MVP — Mechanical Signal System (Phases 1-9) — SHIPPED 2026-04-24</summary>

- [x] Phase 1: Signal Engine Core — Indicators & Vote (6/6 plans) — completed 2026-04-20
- [x] Phase 2: Signal Engine — Sizing, Exits, Pyramiding (5/5 plans) — completed 2026-04-22
- [x] Phase 3: State Persistence with Recovery (4/4 plans) — completed 2026-04-21
- [x] Phase 4: End-to-End Skeleton — Fetch + Orchestrator + CLI (4/4 plans) — completed 2026-04-22
- [x] Phase 5: Dashboard (3/3 plans) — completed 2026-04-22
- [x] Phase 6: Email Notification (4/4 plans) — completed 2026-04-23
- [x] Phase 7: Scheduler + GitHub Actions Deployment (3/3 plans) — completed 2026-04-23
- [x] Phase 8: Hardening — Warning Carry-over, Stale Banner, Crash Email, Config (3/3 plans) — completed 2026-04-23
- [x] Phase 9: Milestone v1.0 Gap Closure (1/1 plan) — completed 2026-04-24

**Archive:** [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
**Audit:** [milestones/v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md)
**Requirements:** [milestones/v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md) (80/80 verified)

</details>

### 📋 v1.1+ (Planned — see PROJECT.md for ideas)

Next milestone TBD. Candidates from v1.0 deferred tech debt:
- F1 full-chain integration test harness
- Holiday-calendar-aware staleness threshold
- Thread-safe `_LAST_LOADED_STATE` if parallel runs appear
- ruff F401 cleanup in notifier.py
- Phase 7 IN-02 README badge placeholder fix
- Phase 7 IN-03 TestWeekdayGate fake quality polish

Run `/gsd-new-milestone` to define v1.1 scope.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Signal Engine Core — Indicators & Vote | v1.0 | 6/6 | Complete | 2026-04-20 |
| 2. Signal Engine — Sizing, Exits, Pyramiding | v1.0 | 5/5 | Complete | 2026-04-22 |
| 3. State Persistence with Recovery | v1.0 | 4/4 | Complete | 2026-04-21 |
| 4. End-to-End Skeleton — Fetch + Orchestrator + CLI | v1.0 | 4/4 | Complete | 2026-04-22 |
| 5. Dashboard | v1.0 | 3/3 | Complete | 2026-04-22 |
| 6. Email Notification | v1.0 | 4/4 | Complete | 2026-04-23 |
| 7. Scheduler + GitHub Actions Deployment | v1.0 | 3/3 | Complete | 2026-04-23 |
| 8. Hardening — Warning Carry-over, Stale Banner, Crash Email | v1.0 | 3/3 | Complete | 2026-04-23 |
| 9. Milestone v1.0 Gap Closure | v1.0 | 1/1 | Complete | 2026-04-24 |

## Operator Decisions Baked In (carried forward to v1.1+)

| Decision | Reflected in |
|----------|--------------|
| GitHub Actions is the PRIMARY deployment path | Phase 7 goal + SCHED-05 success criterion |
| `n_contracts == 0` skips trade + warns (no `max(1,…)` floor) | Phase 2 success criterion 1 + SIZE-04/05 |
| LONG→FLAT (and SHORT→FLAT) closes the open position | Phase 2 success criterion 2 + EXIT-01/02 |
| Trailing stops use intraday high/low (peak updates + hit detection) | Phase 2 success criterion 3 + EXIT-06/07/08/09 |
| Data-fetch errors (yfinance) log + exit rc=2, do NOT email | Phase 9 ERR-01 spec amendment + locked guard test |
| `_resolved_contracts` is runtime-only (underscore-prefix persistence rule) | Phase 8 D-14 + save_state filter |

---

*Roadmap updated: 2026-04-24 after v1.0 milestone archived*
*Ready for: `/gsd-new-milestone` to define v1.1 scope*
