# Roadmap: Trading Signals

**Production:** `https://signals.mwiriadi.me` (DigitalOcean droplet, systemd, nginx + Let's Encrypt, daily 08:00 Sydney signal cycle).

## Milestones

- ✅ **v1.0 MVP — Mechanical Signal System** — Phases 1–9 (shipped 2026-04-24). See [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md).
- ✅ **v1.1 Interactive Trading Workstation** — Phases 10–16 + 16.1 (shipped 2026-04-30). See [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).
- ✅ **v1.2 Trader-Grade Transparency & Validation** — Phases 17, 19, 20, 22, 23, 24, 25, 26, 27 (shipped 2026-05-10). See [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md).
- 📋 **v1.3 — TBD** (planning not yet started — run `/gsd-new-milestone`).

## Phases

<details>
<summary>✅ v1.2 Trader-Grade Transparency & Validation (Phases 17, 19, 20, 22-27) — SHIPPED 2026-05-10</summary>

- [x] Phase 17: Per-signal calculation transparency (1/1 plans) — completed 2026-04-30
- [x] Phase 19: Paper-trade ledger (1/1 plans) — completed 2026-04-30
- [x] Phase 20: Stop-loss monitoring & alerts (1/1 plans) — completed 2026-04-30
- [x] Phase 22: Strategy versioning & audit trail (1/1 plans) — completed 2026-04-29
- [x] Phase 23: 5-year backtest validation gate (7/7 plans) — completed 2026-05-01
- [x] Phase 24: v1.2 codemoot fix phase (1/1 plans) — completed 2026-05-01
- [x] Phase 25: Dashboard UI/UX overhaul (12/12 plans) — completed 2026-05-07
- [x] Phase 26: Phase 25 follow-up scoping fixes (8/8 plans) — completed 2026-05-08
- [x] Phase 27: Code-quality correctness sweep (16/16 plans) — completed 2026-05-10

Phase dirs archived to [milestones/v1.2-phases/](milestones/v1.2-phases/).

</details>

<details>
<summary>✅ v1.1 Interactive Trading Workstation (Phases 10-16 + 16.1) — SHIPPED 2026-04-30</summary>

Phase artifacts still in [phases/](phases/) (operator chose not to archive at v1.1 close). Roadmap: [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).

</details>

<details>
<summary>✅ v1.0 MVP Mechanical Signal System (Phases 1-9) — SHIPPED 2026-04-24</summary>

Phase dirs archived to [milestones/v1.0-phases/](milestones/v1.0-phases/). Roadmap: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md).

</details>

### 📋 v1.3 — Planned

Pending `/gsd-new-milestone` to define scope. Pre-loaded backlog (carried from v1.2 close) below.

## Backlog (carry-forward into v1.3)

### Phase 28: v1.2 deferred UAT closure (proto-Phase 1 of v1.3)

Operator-facing UAT scenarios deferred from v1.2 close. Convert to a formal phase via `/gsd-discuss-phase 28` once v1.3 milestone scope is defined.

**Phase 17 carry-overs (3):**
- ATR(14) hand-recalc to 1e-6 from live `ohlc_window` — operator Excel check against displayed result
- iOS Safari tap-to-toggle on indicator names (mobile interaction verification)
- Cookie persistence across page reload (`tsi_trace_open` allowlist)

**Phase 23 carry-overs (2):**
- End-to-end CLI run with live yfinance data: `python -m backtest --years 5`
- `/backtest` route visual smoke test in browser (chart renders, history view, override form)

**Phase 26 carry-overs (3):**
- Cold-start smoke test on production droplet (UAT-1)
- Multi-tab market scoping browser walkthrough (UAT-2..6 — operator verifies signal/settings/market-test panels scope correctly per `/markets/{m}/{fn}`)

**Acceptance:** All 8 UAT items either completed and recorded in respective phase UAT.md files, or formally accepted as known limitations with explicit operator sign-off.

### Other v1.3 candidates (from v1.2 deferrals)

- **Phase 18** — Multi-user RBAC (deferred from v1.1, again from v1.2; still open if friends-and-family demand emerges)
- **Phase 21** — News integration (`yfinance.Ticker.news` on dashboard + email)
- **Phase 23.5** — Hygiene cleanup (backups, deliverability, per-user TZ)
- **Post-ship polish formalization** — 5 ad-hoc commits 2026-05-08..2026-05-10 (scheduler tz fix, signal status card ladder, v1.1 backtested per-market defaults, trace vote_params, market tab strip refresh) accepted into v1.2 but never phase-tracked. Decide whether to retroactively wrap as a v1.2.1 patch phase or roll forward as accepted state.
- **Retroactive Nyquist VALIDATION.md** — Phases 17, 19, 20, 22, 24, 25, 26 (recommended only if subsystems evolve).
- **Retroactive SECURITY.md** — Phases 17, 19, 20, 22, 23, 24, 25, 26 (currently inherit v1.1 perimeter).
- **`.planning/backtests` path** — CWD-relative; fragile if CLI invoked outside project root (Phase 23 WARNING).

## Progress

| Phase             | Milestone | Plans Complete | Status   | Completed  |
| ----------------- | --------- | -------------- | -------- | ---------- |
| 17. TRACE         | v1.2      | 1/1            | Complete | 2026-04-30 |
| 19. LEDGER        | v1.2      | 1/1            | Complete | 2026-04-30 |
| 20. ALERT         | v1.2      | 1/1            | Complete | 2026-04-30 |
| 22. VERSION       | v1.2      | 1/1            | Complete | 2026-04-29 |
| 23. BACKTEST      | v1.2      | 7/7            | Complete | 2026-05-01 |
| 24. codemoot fix  | v1.2      | 1/1            | Complete | 2026-05-01 |
| 25. UI overhaul   | v1.2      | 12/12          | Complete | 2026-05-07 |
| 26. 25-followup   | v1.2      | 8/8            | Complete | 2026-05-08 |
| 27. quality sweep | v1.2      | 16/16          | Complete | 2026-05-10 |
| 28. v1.2 UAT      | v1.3      | 0/0            | Backlog  | -          |

---

*Last updated: 2026-05-10 after v1.2 milestone close.*
