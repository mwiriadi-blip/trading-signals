# Roadmap: Trading Signals — v1.2 Trader-Grade Transparency & Validation

**Created:** 2026-04-30 (`/gsd-new-milestone` after v1.1 close)
**Milestone:** v1.2 Trader-Grade Transparency & Validation
**Granularity:** fine
**Parallelization:** true
**Coverage:** 22/22 v1.2 requirements mapped (TRACE 5, LEDGER 6, ALERT 4, VERSION 3, BACKTEST 4)

**Core Value (v1.2):** Make every signal *reproducible by hand* and every paper trade *measurable*. Lift the v1.1 hosted dashboard from "tells you what to do" → "shows you exactly why and tracks how it played out". Validate the strategy ships with a 5-year backtest gate before any future logic change. Multi-user, news, and hygiene cleanups deferred to v1.3+.

## Milestones

- [x] **v1.0 MVP — Mechanical Signal System** — Phases 1–9, shipped 2026-04-24. See [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md).
- [x] **v1.1 Interactive Trading Workstation** — Phases 10–16 + 16.1, shipped 2026-04-30. See [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).
- [ ] **v1.2 Trader-Grade Transparency & Validation** — Phases 17, 19, 20, 22, 23 (in progress from 2026-04-30).

## Prerequisites (v1.2)

None operator-blocked. All v1.2 prerequisites land within phases:
- DigitalOcean droplet (already running, v1.1 infra)
- `mwiriadi.me` domain + Resend SPF/DKIM/DMARC (already verified, v1.1)
- 1319-test suite green baseline (v1.1 close)

## Phases

- [x] **Phase 17: Per-signal calculation transparency** — Dashboard renders Inputs / Indicators / Vote panels per instrument so the operator can re-derive the signal by hand (completed 2026-04-30)
- [x] **Phase 19: Paper-trade ledger** — Web form for manual trade entry, per-trade open/closed history, mark-to-market unrealised P&L, aggregate stats (skipping Phase 18 multi-user — single-operator model from v1.1) (completed 2026-04-30)
- [x] **Phase 20: Stop-loss monitoring & alerts** — Daily approaching (within 0.5×ATR) AND hit detection per open paper trade, dedup'd email alerts with state-transition logic (completed 2026-04-30)
- [x] **Phase 22: Strategy versioning & audit trail** — `STRATEGY_VERSION` constant in `system_params.py`, every signal/trade row tagged so historical state stays interpretable across logic changes (completed 2026-04-29)
- [x] **Phase 23: 5-year backtest validation gate** — Walk-forward backtest over 5y of yfinance data, `>100% cumulative return` pass criterion, `/backtest` route on dashboard with metrics + pass/fail badge (completed 2026-05-01)
- [x] **Phase 24: v1.2 codemoot fix phase** — Fix 3 verified bugs + cleanup 7 code-quality items from post-milestone codemoot review (completed 2026-05-01)

## Phase Details

### Phase 17: Per-signal calculation transparency
**Goal:** Make today's signal reproducible from the dashboard alone — operator can plug numbers into Excel/Bloomberg/IG and re-derive identical indicator values without reading source code.
**Depends on:** Nothing (read-only dashboard refactor; can run in parallel with Phase 22).
**Requirements:** TRACE-01, TRACE-02, TRACE-03, TRACE-04, TRACE-05
**Success Criteria** (what must be TRUE):
1. Three new panels (Inputs / Indicators / Vote) render per instrument on `https://signals.mwiriadi.me/`
2. The Inputs panel displays the OHLC bars used by ATR(14), ADX(20), Mom-12 (today + prior 19 bars at minimum)
3. The Indicators panel displays TR, ATR, +DI, -DI, ADX, Mom1/3/12, RVol with formula + numeric result
4. The Vote panel shows the 2-of-3 momentum vote breakdown + ADX gate (with actual ADX numeric)
5. Operator can manually re-derive ATR(14) from the displayed OHLC values and match the displayed ATR result to 1e-6 tolerance
6. No new I/O or state mutation introduced — the panels are pure render from existing state + indicator recompute
7. Forbidden-imports AST guard extended for the new dashboard.py code paths

### Phase 19: Paper-trade ledger
**Goal:** Operator records the trades they've actually placed (or plan to), tracks open positions with live mark-to-market P&L, and sees a closed-trade history with realised P&L and aggregate stats.
**Depends on:** Phase 22 (paper trade rows must include `strategy_version` per VERSION-03; if 22 lands first, ledger writes the field on entry; if 19 lands first, migrate the field on Phase 22 deploy).
**Requirements:** LEDGER-01, LEDGER-02, LEDGER-03, LEDGER-04, LEDGER-05, LEDGER-06
**Success Criteria** (what must be TRUE):
1. POST `/paper-trade/open` form on dashboard accepts {instrument, side, entry_dt, entry_price, contracts, stop_price?} → validated server-side → appended to `state.paper_trades`
2. POST `/paper-trade/close` form accepts {trade_id, exit_dt, exit_price} → server computes realised P&L → flips `status=open` to `status=closed`
3. Closed rows are immutable (no edit form rendered, server returns 405 to PUT/PATCH)
4. "Open Paper Trades" table renders all `status=open` rows with current price + unrealised P&L (mark-to-market using today's close)
5. "Closed Paper Trades" table renders all `status=closed` rows sortable by exit date desc
6. Aggregate stats line displays total realised P&L, total unrealised P&L, win count, loss count, win rate %
7. Atomic-write contract preserved — `paper_trades` writes go through the same `state_manager._atomic_write` as positions/equity_history

### Phase 20: Stop-loss monitoring & alerts
**Goal:** When a paper trade with a stop price approaches or hits the stop, the operator gets a dedicated email alert (separate from the daily signal email) at most once per state transition.
**Depends on:** Phase 19 (needs `paper_trades` array with `stop_price` and `last_alert_state` fields).
**Requirements:** ALERT-01, ALERT-02, ALERT-03, ALERT-04
**Success Criteria** (what must be TRUE):
1. On every daily run, for each open paper trade with non-null `stop_price`, the system computes one of {CLEAR, APPROACHING, HIT}
2. State transition `CLEAR → APPROACHING` or `* → HIT` triggers a `[!stop]`-prefixed email to `OPERATOR_RECOVERY_EMAIL` (with daily-signal-email-style fallback if missing)
3. Same state on consecutive days does NOT re-trigger the email (deduplication via `last_alert_state` field)
4. Dashboard "Alerts" pane renders each open trade's current alert state with green/amber/red color
5. APPROACHING threshold uses 0.5 × current ATR(14); HIT detection uses today's High (for SHORT stops) and today's Low (for LONG stops) per the existing intraday-H/L exit pattern from Phase 2
6. Alert-send failures NEVER crash the daily run (existing never-crash pattern from notifier.py)

### Phase 22: Strategy versioning & audit trail
**Goal:** Every signal output and paper trade row carries a `strategy_version` tag, so historical results stay interpretable when the signal logic changes (e.g., Mom thresholds, ADX gate cutoff).
**Depends on:** Nothing (standalone, can land in parallel with Phase 17).
**Requirements:** VERSION-01, VERSION-02, VERSION-03
**Success Criteria** (what must be TRUE):
1. `STRATEGY_VERSION = 'v1.2.0'` constant added to `system_params.py`
2. `state.signals[<instrument>].strategy_version` field populated on every write (matching the constant at write-time)
3. `state.paper_trades[].strategy_version` field populated on every entry (matching the constant at entry datetime)
4. Migration on first v1.2 deploy: existing signal rows stamped `v1.1.0`; existing paper_trades rows (if Phase 19 already shipped) stamped `v1.1.0` retroactively
5. `docs/STRATEGY-CHANGELOG.md` created with v1.0.0 / v1.1.0 / v1.2.0 entries explaining what each version represents
6. Bumping `STRATEGY_VERSION` does NOT mutate historical rows — closed paper trades retain the version they were entered under

### Phase 23: 5-year backtest validation gate
**Goal:** Validate the strategy ships every change with a 5-year walk-forward backtest. Pass criterion is `cumulative return > 100% over 5y`. Operator views report on `/backtest` route; failures block the strategy change socially (operator expected to revert).
**Depends on:** Phase 22 (results tagged with `strategy_version`).
**Requirements:** BACKTEST-01, BACKTEST-02, BACKTEST-03, BACKTEST-04
**Success Criteria** (what must be TRUE):
1. New `backtest/` module — pure compute, hex-boundary respected (no `state_manager`, no `notifier`, no I/O outside its own bound CLI entry)
2. Walks 5y of OHLCV per instrument from yfinance, applies live `signal_engine.compute_indicators` + `get_signal`, simulates open/close per signal change with trailing stops + pyramid rules from `sizing_engine`
3. Aggregates per-instrument and combined: cumulative return %, Sharpe (daily), max drawdown, win rate, expectancy, total trades
4. `/backtest` route renders equity curve (Chart.js, same lib as Phase 5 dashboard), metrics table, **pass/fail badge** (`PASS` if cumulative return > 100%, `FAIL` otherwise)
5. CLI: `python -m backtest --years 5` re-runs the backtest, prints summary, persists JSON to `.planning/backtests/<strategy_version>-<timestamp>.json`
6. Result tagged with `strategy_version` from VERSION-01; multiple backtest runs across versions visible in `/backtest?history=true` view

**Plans:** 7/7 plans complete

Plans:
- [x] 23-01-wave0-scaffolding-PLAN.md — Wave 0 scaffolding: pyarrow pin, backtest/ skeleton, AST guard extension, golden fixture, test skeletons
- [x] 23-02-data-fetcher-PLAN.md — Wave 1A backtest/data_fetcher.py (yfinance + parquet cache + <5y bail)
- [x] 23-03-simulator-PLAN.md — Wave 1B backtest/simulator.py (bar-by-bar replay reusing signal_engine + sizing_engine)
- [x] 23-04-metrics-PLAN.md — Wave 1C backtest/metrics.py (Sharpe / max DD / win rate / expectancy / cum return)
- [x] 23-05-render-PLAN.md — Wave 2A backtest/render.py (3-tab HTML report + history + override form)
- [x] 23-06-cli-PLAN.md — Wave 2B backtest/cli.py (argparse + JSON write + exit codes + log lines)
- [x] 23-07-web-routes-PLAN.md — Wave 2C web/routes/backtest.py (4 routes + path-traversal + cookie auth)


## Phase Dependencies (build order)

```
                  Wave 1 (parallel)
                  ┌────────────┐  ┌────────────┐
                  │ Phase 17   │  │ Phase 22   │
                  │ TRACE      │  │ VERSION    │
                  └─────┬──────┘  └─────┬──────┘
                        │               │
                        │   Wave 2     │
                        │   ┌──────────▼─┐
                        │   │ Phase 19   │
                        │   │ LEDGER     │
                        │   └─────┬──────┘
                        │         │
                        │   Wave 3│
                        │   ┌─────▼──────┐
                        │   │ Phase 20   │
                        │   │ ALERT      │
                        │   └────────────┘
                        │
                        │   Wave 4 (depends on 22)
                        │   ┌────────────┐
                        └──>│ Phase 23   │
                            │ BACKTEST   │
                            └────────────┘
```

**Wave 1 (parallel):** Phase 17 (TRACE) + Phase 22 (VERSION). Disjoint files (Phase 17 = dashboard.py + indicator-trace; Phase 22 = system_params.py + state_manager.py migration). Can land same day.

**Wave 2:** Phase 19 (LEDGER). Needs `STRATEGY_VERSION` constant from Phase 22 to stamp paper trade rows. Touches state.json schema (add `paper_trades` array).

**Wave 3:** Phase 20 (ALERT). Needs `paper_trades` schema from Phase 19 (specifically `stop_price` + `last_alert_state` fields).

**Wave 4 (parallel with Wave 2/3 from Phase 22 onwards):** Phase 23 (BACKTEST). Needs `STRATEGY_VERSION` for tagging; otherwise standalone (own `backtest/` module). Largest single phase — likely the longest in v1.2.

## Progress

[░░░░░░░░░░░░░░░░] 0% (0/5 phases complete)

## Coverage Validation

| REQ-ID | Phase | Mapped |
|--------|-------|--------|
| TRACE-01..05 | 17 | ✓ (5/5) |
| LEDGER-01..06 | 19 | ✓ (6/6) |
| ALERT-01..04 | 20 | ✓ (4/4) |
| VERSION-01..03 | 22 | ✓ (3/3) |
| BACKTEST-01..04 | 23 | ✓ (4/4) |

**Total:** 22/22 mapped, 0 orphans, 0 duplicates.

## Operator Decisions Baked In (v1.2)

- **D-01:** Skip Phase 18 multi-user — single-operator model from v1.1 sufficient through v1.2; revisit at v1.3 if friends-and-family demand emerges.
- **D-02:** Skip Phase 21 news integration — defer to v1.3+ as supplemental feature; operator focus stays on calc transparency + measurement.
- **D-03:** Skip Phase 23.5 hygiene — defer to v1.3+ when v1.2 functional surface stabilizes; current backup story (git-tracked state.json + droplet snapshot) acceptable.
- **D-04:** Backtest pass criterion = `cumulative return > 100% over 5y` — strict ledger-style threshold per SPEC.md operator brainstorm 2026-04-29; Sharpe / drawdown / win rate displayed but not gating.
- **D-05:** `STRATEGY_VERSION` semver — bumped on signal-logic change only (Mom thresholds, ADX gate, sizing weights). Bumped to `v1.2.0` at v1.2 launch.

## Carried-Forward Operator Decisions from v1.0/v1.1

- **Signal-only.** No broker API, ever (hard constraint).
- **Daily cadence only.** No intraday data; stop-loss alerts fire on next daily run.
- **Python.** Locked.
- **DO droplet hosting.** No serverless, no container orchestration.
- **Hex-boundary architecture.** Pure-math modules cannot import adapters.
- **Atomic state writes.** tempfile + fsync + os.replace, contention-guarded.
- **Email never-crash.** Resend failures logged, never abort daily run.
