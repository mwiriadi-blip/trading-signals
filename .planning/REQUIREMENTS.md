# Requirements — Trading Signals v1.2

**Milestone:** v1.2 — Trader-Grade Transparency & Validation
**Defined:** 2026-04-30 (operator selected 5 phases from SPEC.md §v1.2+ sketch via `/gsd-new-milestone`)
**Total:** 22 requirements across 5 categories
**Mapped to phases:** 22/22
**Coverage:** 100% (0 orphans, 0 duplicates)

**Core value (v1.2):** Make every signal *reproducible by hand* and every paper trade *measurable*. Lift the v1.1 hosted dashboard from "tells you what to do" → "shows you exactly why and tracks how it played out". Validate the strategy ships with a 5-year backtest gate before any future logic change.

## Categories at a glance

| Code | Phase | Count | Description |
|------|-------|-------|-------------|
| TRACE | 17 | 5 | Per-signal calculation transparency on dashboard |
| LEDGER | 19 | 6 | Paper-trade journal with manual entry, per-user history, P&L |
| ALERT | 20 | 4 | Stop-loss monitoring + dedup'd email alerts |
| VERSION | 22 | 3 | `STRATEGY_VERSION` constant + signal/trade row tagging |
| BACKTEST | 23 | 4 | 5-year walk-forward backtest with `>100% cumulative return` pass gate |

## v1.2 Requirements

### TRACE — Per-signal calculation transparency (Phase 17)

- [ ] **TRACE-01** — Dashboard renders an "Inputs" panel per instrument showing the OHLC values used for today's signal (today's bar + the prior-N bars needed by ATR(14), ADX(20), Mom-12). Reproducible: operator can plug values into Excel/Bloomberg/IG and re-derive identical indicator values.
- [ ] **TRACE-02** — Dashboard renders an "Indicators" panel per instrument showing TR, ATR(14), +DI(20), -DI(20), ADX(20), Mom1, Mom3, Mom12, RVol(20) — each with the formula and the displayed numeric result. Hover-tooltip reveals the formula.
- [ ] **TRACE-03** — Dashboard renders a "Vote" panel showing the 2-of-3 momentum vote breakdown (Mom1 sign, Mom3 sign, Mom12 sign) and the ADX gate (≥25 PASS / <25 FLAT) with the gate's actual ADX value.
- [ ] **TRACE-04** — All three panels (Inputs / Indicators / Vote) render without server-side state mutation — pure read from `state.json` + indicator recompute on render. Survives `--test` mode.
- [ ] **TRACE-05** — Forbidden-imports AST guard for `dashboard.py` extended: trace panels must not import `state_manager`, `os.environ`, or any I/O — operator-confidence test stays as a hex-boundary check.

### LEDGER — Paper-trade ledger (Phase 19)

- [ ] **LEDGER-01** — Web form on dashboard for manual paper trade entry: instrument, side (LONG/SHORT), entry datetime, entry price, contracts, stop price (optional). Validated server-side; rejects future dates, negative prices, contracts ≤ 0.
- [ ] **LEDGER-02** — Per-trade entry persisted to a new `paper_trades` array in `state.json` (not a separate file — leverages existing atomic-write infrastructure). Each row: `id`, `instrument`, `side`, `entry_dt`, `entry_price`, `contracts`, `stop_price`, `status` (open/closed), `exit_dt` (nullable), `exit_price` (nullable), `pnl` (nullable), `strategy_version` (from VERSION-01).
- [ ] **LEDGER-03** — "Open Paper Trades" table on dashboard renders all `status=open` rows with current price + unrealised P&L. Mark-to-market uses the same close price the signal engine used for today.
- [ ] **LEDGER-04** — "Closed Paper Trades" table on dashboard renders all `status=closed` rows with realised P&L, days held, side, instrument, entry/exit. Sortable by exit date desc.
- [ ] **LEDGER-05** — Web form to close an open paper trade: select trade, enter exit price + exit datetime, server computes realised P&L and flips `status=closed`. Closed rows are immutable (no edit form).
- [ ] **LEDGER-06** — Aggregate P&L stat displayed: total realised P&L, total unrealised P&L, win count, loss count, win rate. Updates on every trade close.

### ALERT — Stop-loss monitoring & alerts (Phase 20)

- [ ] **ALERT-01** — On every daily run, for each open paper trade with a non-null `stop_price`, compute distance: if `(side==LONG AND today_low <= stop_price)` OR `(side==SHORT AND today_high >= stop_price)` → mark **HIT**; else if `abs(today_close - stop_price) <= 0.5 × ATR(14)` → mark **APPROACHING**; else **CLEAR**.
- [ ] **ALERT-02** — On state transition `CLEAR → APPROACHING` or `* → HIT`, send a dedicated email alert to `OPERATOR_RECOVERY_EMAIL` (or `SIGNALS_EMAIL_TO`). Subject prefix `[!stop]`. Body: instrument, side, entry, current stop, today's close, distance in ATR units, link to dashboard.
- [ ] **ALERT-03** — Alerts are deduplicated per-trade-per-state: once a trade's stop is **APPROACHING**, the daily emails do not re-send the alert until the state changes to **CLEAR** or **HIT**. Persisted in `paper_trades[].last_alert_state` field.
- [ ] **ALERT-04** — Dashboard renders an "Alerts" pane showing each open trade's current alert state (CLEAR / APPROACHING / HIT) with a colored indicator (green/amber/red).

### VERSION — Strategy versioning & audit trail (Phase 22)

- [x] **VERSION-01** — `STRATEGY_VERSION` constant added to `system_params.py` with semver pattern (`v1.2.0` at v1.2 launch). Bumped on any signal-logic change (Mom thresholds, ADX gate, sizing weights, etc.). Version bumps documented in `docs/STRATEGY-CHANGELOG.md`.
- [x] **VERSION-02** — Every signal row written to `state.signals[<instrument>]` includes `strategy_version` matching the constant at write-time. Migration: existing rows on first v1.2 deploy stamped with `v1.1.0`.
- [ ] **VERSION-03** — Every paper trade row in `state.paper_trades` (LEDGER-02) includes `strategy_version` matching the constant at the trade's entry datetime. Closed trades retain the version they were entered under, even if `STRATEGY_VERSION` later bumps.

### BACKTEST — 5-year backtest validation gate (Phase 23)

- [ ] **BACKTEST-01** — `backtest/` module added (hex-boundary respected: pure compute, no I/O, no `state_manager` import). Walks 5 years of OHLCV per instrument from yfinance, applies the live signal engine (`signal_engine.compute_indicators` + `get_signal`) bar-by-bar, simulates open/close per signal change, applies trailing stops + pyramid rules from `sizing_engine`, accumulates P&L.
- [ ] **BACKTEST-02** — Runs across both instruments (SPI 200 + AUD/USD), aggregates equity curve, computes metrics: cumulative return %, Sharpe (daily), max drawdown, win rate, expectancy, total trades. Each result tagged with `strategy_version` (VERSION-01).
- [ ] **BACKTEST-03** — `/backtest` route on dashboard renders the most recent backtest report: equity curve chart (Chart.js), metrics table, pass/fail badge. **Pass criterion: cumulative return > 100% over 5y**. Other metrics displayed but not gating.
- [ ] **BACKTEST-04** — Backtest re-runnable on demand via CLI (`python -m backtest --years 5`) and on every `STRATEGY_VERSION` bump. Result persisted to `.planning/backtests/<strategy_version>-<timestamp>.json` for audit history. Fail-loud: if cumulative return ≤ 100%, the report renders with a red "FAIL" badge and the operator is expected to revert the strategy change.

---

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| TRACE-01 | 17 | Pending |
| TRACE-02 | 17 | Pending |
| TRACE-03 | 17 | Pending |
| TRACE-04 | 17 | Pending |
| TRACE-05 | 17 | Pending |
| LEDGER-01 | 19 | Pending |
| LEDGER-02 | 19 | Pending |
| LEDGER-03 | 19 | Pending |
| LEDGER-04 | 19 | Pending |
| LEDGER-05 | 19 | Pending |
| LEDGER-06 | 19 | Pending |
| ALERT-01 | 20 | Pending |
| ALERT-02 | 20 | Pending |
| ALERT-03 | 20 | Pending |
| ALERT-04 | 20 | Pending |
| VERSION-01 | 22 | Complete |
| VERSION-02 | 22 | Complete |
| VERSION-03 | 22 | Pending |
| BACKTEST-01 | 23 | Pending |
| BACKTEST-02 | 23 | Pending |
| BACKTEST-03 | 23 | Pending |
| BACKTEST-04 | 23 | Pending |

## Out of scope (deferred to v1.3 or later)

- **Phase 18** — Multi-user data model (RBAC, `users` table). Single-operator model from v1.1 sufficient through v1.2.
- **Phase 21** — News integration (`yfinance.Ticker.news` on dashboard + email). Operator preference: focus v1.2 on calc transparency + measurement; news is supplemental.
- **Phase 23.5** — Hygiene cleanup (backups, deliverability, per-user TZ). Lands when the v1.2 functional surface stabilizes.

See `SPEC.md §v1.2+ Long-Term Roadmap` for the full operator brainstorm and the v2.0 horizon (top-of-volume market expansion, broker API → never).
