---
phase: 19
phase_name: Paper-trade ledger
milestone: v1.2
created: 2026-04-30
status: locked
requirements: [LEDGER-01, LEDGER-02, LEDGER-03, LEDGER-04, LEDGER-05, LEDGER-06, VERSION-03]
source: ROADMAP.md v1.2 Phase 19 Success Criteria + REQUIREMENTS.md LEDGER namespace + operator discuss-phase 2026-04-30
---

# Phase 19 — Paper-trade Ledger (CONTEXT)

## Goal

Operator records the trades they have actually placed (or plan to place) at their broker. Open positions track unrealised mark-to-market P&L using today's close price the signal engine consumed. Closed positions are immutable history with realised P&L. An at-a-glance aggregate stat bar below the page header summarises performance. Every row carries the `strategy_version` it was entered under (VERSION-03), so changing the signal logic later does not retroactively rewrite the operator's trade history.

## Scope

**In:**
- New `state.paper_trades = []` array, schema bump 5 → 6 with `_migrate_v5_to_v6`
- POST `/paper-trade/open` — server-validated entry form (HTMX swap)
- PATCH `/paper-trade/<id>` — edit-in-place for open rows (operator typo fix)
- DELETE `/paper-trade/<id>` — delete-typo for open rows
- POST `/paper-trade/<id>/close` — server-computed realised P&L; closed rows immutable thereafter
- "Open Paper Trades" table on dashboard with mark-to-market unrealised P&L per row
- "Closed Paper Trades" table on dashboard, sortable by exit date desc
- "Aggregate stats" badge bar below the header (always visible) — realised, unrealised, win count, loss count, win rate
- Composite human-readable trade IDs of the form `<INSTRUMENT>-<YYYYMMDD>-<NNN>`
- VERSION-03 wiring: every entry write tags the row with `system_params.STRATEGY_VERSION` at the moment of write (fresh attribute access per Phase 22 LEARNINGS)

**Out (deferred to v1.3+):**
- Per-trade tags / free-text notes (operator can add later if useful)
- CSV / JSON export
- Filter UI for closed-trades table (instrument, date range, strategy_version)
- Currency / FX-aware P&L when broker quotes in non-AUD (today: SPI200 P&L is AUD; AUDUSD P&L is in USD nominal × 10,000 notional, and we display USD-as-AUD per CLAUDE.md without conversion — operator's mental model)
- Tax-lot accounting / wash-sale rules
- Real-time price feed beyond the daily-run close

**Out (different phases):**
- Stop-loss alerts (Phase 20 reads `paper_trades[].stop_price` and `last_alert_state`)
- Backtest replay against the same ledger (Phase 23)
- Multi-user trade journals (Phase 18 — already deferred to v1.3)

## Locked decisions

### D-01 — Trade ID format

**Composite human-readable: `<INSTRUMENT>-<YYYYMMDD>-<NNN>`.** Examples: `SPI200-20260430-001`, `AUDUSD-20260430-002`, `SPI200-20260501-001`.

- `<INSTRUMENT>` is the project key from `system_params` (`SPI200` or `AUDUSD`)
- `<YYYYMMDD>` is the entry-date in AWST (operator's TZ — matches Phase 7 `_get_process_tzname` convention)
- `<NNN>` is a per-instrument-per-day zero-padded counter starting at `001`, capped at `999/day/instrument` (acceptable headroom — paper-trade workflow is hand-driven)

Counter is computed inside the `mutate_state` lock at write time (D-15) — read existing `paper_trades`, filter by `instrument` + entry-date, find max counter, increment by one. Atomicity guaranteed by the existing Phase 14 `flock`-on-the-state-file kernel.

Rejected: UUID4 (unreadable in URL bar / log lines / verbal reference); flat sequential int (no information density; harder to grep history).

### D-02 — Cost split (round-trip cost handling)

**Half on entry, half on exit (Phase 2 D-13 precedent).** The round-trip cost from CLAUDE.md (`$6 AUD` SPI200, `$5 AUD` AUDUSD) is split symmetrically:

- On entry: `entry_cost_aud = round_trip_cost / 2` is recorded on the row but is NOT a separate ledger entry
- On `compute_unrealised_pnl` (open rows): subtracts `cost / 2` from the gross P&L so the operator sees the entry-side cost from day one
- On close: subtracts the *other* `cost / 2` from the gross realised P&L

This matches the Phase 2 invariant that `compute_unrealised_pnl(..., cost_aud_open)` already takes a half-cost; we reuse the function shape.

Rejected: full cost on entry (open rows look worse than reality on day 1, deviates from Phase 2); full cost on exit (optimistic open view, deviates from Phase 2).

### D-03 — Close form UX flow

**Click row → separate close form below the open trades table.** When the operator clicks an open-row, the row's `data-trade-id` populates a single dedicated close-form section that lives directly below the open trades table. The close form has fields `exit_dt` (default = now), `exit_price` (required), and `[Close] [Cancel]` buttons. Submitting POSTs to `/paper-trade/<id>/close` and HTMX swaps the open trades table + closed trades table + stats bar.

Rejected: inline expand-row (HTMX `hx-swap="innerHTML"` targeting the row — operator wanted explicit separate form; less mobile-tap-fat-finger risk); native `<dialog>` modal (extra dismiss/escape handling, less mobile-friendly).

### D-04 — Validation rules (server-side)

**Strict.** Server-side validation rejects entries that violate any of:

- `entry_dt` is in the future (datetime > now in AWST → 422 with explicit reason)
- `entry_price <= 0` → 422
- `contracts <= 0` → 422
- `instrument` not in `{'SPI200', 'AUDUSD'}` → 422
- `side` not in `{'LONG', 'SHORT'}` → 422
- For `SPI200`: `contracts` must be an integer (the SPI mini contract is whole-unit) → 422 if fractional
- For `AUDUSD`: `contracts` may be a float (notional units) → no fractional rejection
- If `stop_price` provided AND `side == LONG`: `stop_price < entry_price` (else 422 — stop on wrong side)
- If `stop_price` provided AND `side == SHORT`: `stop_price > entry_price` (else 422)
- `stop_price <= 0` → 422 (when provided)

The validation helper lives in `web/routes/paper_trades.py` as `_validate_open_form(form_dict) -> dict | HTTPException`. Pure function, table-driven, no I/O.

For close form:
- `exit_dt` may be in the past relative to `now` (operator can back-fill a close that happened earlier in the day) but MUST be `>= entry_dt` of the trade being closed → 422
- `exit_price > 0` → 422 if violated

Rejected: permissive (typos slip through the form into ledger history); strict-with-override-flag (footgun — paper trading should be high-friction on weird scenarios; operator can edit state.json on droplet for true emergencies).

### D-05 — Open-row mutation policy

**Edit allowed, delete allowed for `status=open` rows. Closed rows immutable.**

- PATCH `/paper-trade/<id>` accepts the same fields as the open form (instrument, side, entry_dt, entry_price, contracts, stop_price). Server runs the D-04 validators identically; if the row is `status=closed`, returns 405 with body `closed rows are immutable`.
- DELETE `/paper-trade/<id>` removes the row entirely from `state.paper_trades`. If the row is `status=closed`, returns 405 same body.
- An edit overwrites `strategy_version` with the current `system_params.STRATEGY_VERSION` — acceptable because the entry hasn't been resolved into history yet. Document in the response toast: "Trade edited; strategy_version refreshed to vX.Y.Z."

LEDGER-04 row-immutability invariant guarded by a route-layer test: PATCH and DELETE on a closed row return exactly 405 with the literal body string. PUT also returns 405 (we don't implement PUT — but the FastAPI default for an undefined method is 405 anyway).

Rejected: edit allowed but delete forbidden (forces operator to close a typo at entry-price = zero P&L pollution); both forbidden (defeats the point of a UI — operator would need to ssh to droplet and edit state.json).

### D-06 — Aggregate stats placement

**Top of page, immediately below the dashboard header. Sticky on scroll.** A horizontal badge bar:

```
┌─ Realised: +$1,234.50 ──┬─ Unrealised: -$56.20 ──┬─ Wins: 8 ──┬─ Losses: 3 ──┬─ Win rate: 73% ─┐
```

- Realised = sum of all `paper_trades[*].realised_pnl` where `status=closed`
- Unrealised = sum of `compute_unrealised_pnl(...)` over all `status=open` rows
- Wins = count of `status=closed` rows where `realised_pnl > 0`
- Losses = count of `status=closed` rows where `realised_pnl < 0` (zero-P&L trades are not wins or losses)
- Win rate = `wins / (wins + losses)` displayed as integer percent; "—" when wins+losses == 0

CSS: `position: sticky; top: 0;` on a `<aside class="stats-bar">` element so the bar stays visible as the operator scrolls into closed-history. Mobile: wraps to two rows (3 stats per row) — same `display: flex; flex-wrap: wrap` pattern Phase 17 uses for the trace badges.

Computation runs in a new pure helper `_compute_aggregate_stats(paper_trades: list[dict], signals: dict) -> dict` in `dashboard.py` — primitives in / primitive out, hex-boundary safe.

Rejected: above the open trades table (scrolls out of view as operator drills into closed history); below the closed table (hidden on first glance); inside the existing signal-card row (couples two unrelated UI concerns).

### D-07 — Mark-to-market price source

**`state.signals[<instrument>].last_close`** for unrealised P&L on every open row.

- Pure read off the state dict — no new I/O, no live yfinance, no network from the render path
- Survives `--test` mode unchanged
- On weekends / public holidays this is last weekday's close (acceptable — Phase 2 same)
- Hex-boundary preserved: `dashboard.py` continues to NOT import `data_fetcher` / `yfinance` / `state_manager`
- Edge case: if `state.signals[<inst>]` is missing or `last_close` is `None` (truly fresh state.json, instrument never been seen), unrealised P&L for that row is rendered as `n/a (no close price yet)` — matches Phase 17 D-06 explicit-reason precedent

Rejected: live yfinance fetch on render (violates hex-boundary, breaks `--test`, network failure breaks render); operator-supplied as-of price (scope creep, more UI surface, requires client-side recompute).

### D-08 — Schema bump 5 → 6

`STATE_SCHEMA_VERSION` bumps `5` (Phase 17) → `6`. New migration `_migrate_v5_to_v6` registered in `MIGRATIONS[6]` (between key 5 and the end of the dispatch table). Body:

```python
def _migrate_v5_to_v6(s: dict) -> dict:
  '''Phase 19 (v1.2): introduce paper_trades array.

  v5 rows had no paper_trades concept. Add empty list at top level.
  Idempotent: never overwrite an existing populated paper_trades.
  D-15 silent migration: no append_warning, no log line.
  '''
  if 'paper_trades' not in s:
    s['paper_trades'] = []
  return s
```

Same migration test pattern as Phase 17/22 §D-05 (idempotent, preserves-other-fields, full-walk v0→v6).

### D-09 — `state.paper_trades[]` row shape

Each row is a dict with this exact key set:

| Field | Type | Notes |
|-------|------|-------|
| `id` | str | Composite per D-01 (`SPI200-20260430-001`) |
| `instrument` | str | `'SPI200'` or `'AUDUSD'` |
| `side` | str | `'LONG'` or `'SHORT'` |
| `entry_dt` | str | ISO8601 in AWST (`'2026-04-30T14:23:00+08:00'`) |
| `entry_price` | float | > 0 |
| `contracts` | int (SPI) \| float (AUDUSD) | > 0 |
| `stop_price` | float \| None | optional; side-validated per D-04 |
| `entry_cost_aud` | float | half of `round_trip_cost` per D-02 |
| `status` | str | `'open'` or `'closed'` |
| `exit_dt` | str \| None | populated on close |
| `exit_price` | float \| None | populated on close |
| `realised_pnl` | float \| None | populated on close per D-11 |
| `strategy_version` | str | `system_params.STRATEGY_VERSION` at write/edit time per VERSION-03 |

Validators reject any entry that introduces unknown keys (defensive — pinned by `test_paper_trade_row_keys_strict`).

### D-10 — Cost / multiplier constants

Already in CLAUDE.md D-11/D-13 + `system_params.py` from Phase 2. Phase 19 imports them inside `pnl_engine.py` (new pure-math module) and `web/routes/paper_trades.py`:

- `SPI200_MULTIPLIER_PER_POINT = 5.0`  *(AUD per SPI 200 mini index point)*
- `SPI200_ROUND_TRIP_COST_AUD = 6.0`
- `AUDUSD_NOTIONAL_UNITS = 10000.0`
- `AUDUSD_ROUND_TRIP_COST_AUD = 5.0`

### D-11 — P&L formulas

**LONG:**
- Unrealised (`status=open`): `(last_close − entry_price) × contracts × multiplier − entry_cost_aud`
- Realised (`status=closed`): `(exit_price − entry_price) × contracts × multiplier − round_trip_cost_aud`  *(both halves applied at close-time)*

**SHORT:**
- Unrealised: `(entry_price − last_close) × contracts × multiplier − entry_cost_aud`
- Realised: `(entry_price − exit_price) × contracts × multiplier − round_trip_cost_aud`

Where `multiplier`:
- `SPI200`: `SPI200_MULTIPLIER_PER_POINT` (= 5.0)
- `AUDUSD`: `AUDUSD_NOTIONAL_UNITS` (= 10000.0; AUDUSD price is the FX rate, P&L denominated in USD with the convention "USD-as-AUD" per CLAUDE.md)

These live in a new pure-math module `pnl_engine.py` (mirrors the `signal_engine.py` / `sizing_engine.py` hex-pure pattern). Functions:

```python
def compute_unrealised_pnl(side: str, entry_price: float, last_close: float,
                           contracts: float, multiplier: float, entry_cost_aud: float) -> float: ...

def compute_realised_pnl(side: str, entry_price: float, exit_price: float,
                         contracts: float, multiplier: float, round_trip_cost_aud: float) -> float: ...
```

Both functions are pure (no `datetime.now`, no env vars, no module-level state). Forbidden imports for `pnl_engine.py`: same list as `sizing_engine.py` — `state_manager`, `notifier`, `dashboard`, `main`, `requests`, `datetime`, `os`. Enforced by extending `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent`.

### D-12 — Routes (FastAPI)

| Method | Path | Handler |
|--------|------|---------|
| `GET` | `/` (existing) | renders dashboard with both tables + stats bar |
| `GET` | `/paper-trades` | returns rendered HTML fragment of the two tables + stats bar (HTMX hx-target after every mutation) |
| `POST` | `/paper-trade/open` | validates entry form (D-04), writes via `mutate_state`, returns updated tables HTML |
| `PATCH` | `/paper-trade/<id>` | validates edit form, writes via `mutate_state`, returns updated tables HTML; 405 if closed |
| `DELETE` | `/paper-trade/<id>` | removes row via `mutate_state`, returns updated tables HTML; 405 if closed |
| `POST` | `/paper-trade/<id>/close` | validates close form, computes realised P&L via `pnl_engine.compute_realised_pnl`, writes via `mutate_state`, returns updated tables HTML |

All mutating routes auth-gate per Phase 16.1 cookie-session middleware (already in place). All return HTML fragments (HTMX) for in-place swap.

A new module `web/routes/paper_trades.py` owns the four mutation routes; `web/routes/dashboard.py` continues to own the GET dashboard render. Mount in `web/app.py` adjacent to the existing trade-journal mount: `app.use('/paper-trade', require('./routes/paper_trades')(deps))` — same pattern as Phase 14.

### D-13 — HTMX swap targets

- Entry form `<form hx-post="/paper-trade/open" hx-target="#trades-region" hx-swap="outerHTML">` — `#trades-region` wraps stats bar + open table + close form + closed table; replaces the entire region atomically.
- Edit-row form: same target.
- Delete row: `hx-confirm="Delete this open paper trade?"` + same target.
- Close form: same target.

Single swap target keeps the three tables (stats / open / closed) in sync — each mutation reflows all three.

### D-14 — Hex-boundary preservation

`dashboard.py` continues to NOT import `system_params` / `state_manager` / `data_fetcher` / `signal_engine` / `yfinance` / `web.middleware`. Adds `pnl_engine` to the import list — `pnl_engine` is pure-math (same hex-tier as `signal_engine` and `sizing_engine`), so this is safe per the existing rule "pure-math modules may import each other; adapters cannot import other adapters".

`pnl_engine.py` itself imports nothing project-internal beyond `system_params` (for the multiplier / cost constants). The forbidden-imports AST guard test `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` extends to walk `pnl_engine.py` against the same forbidden-list pattern as `sizing_engine.py`.

`web/routes/paper_trades.py` is an adapter — it imports `pnl_engine`, `state_manager.mutate_state`, and `system_params.STRATEGY_VERSION`. This is correct hex-lite layering (route adapter calls pure-math + state-IO).

### D-15 — Concurrency & atomicity

Every mutation route goes through `state_manager.mutate_state(mutator, path)` from Phase 14 D-14 — holds `flock(LOCK_EX)` across the full read-modify-write cycle. The mutator closure receives the freshly-loaded state dict and applies the operation:

- **Open**: validate D-04, generate D-01 ID inside the closure (read existing rows for that instrument-date, find max counter, +1), build the row, append.
- **Edit**: find row by ID, assert `status=open`, validate D-04 with the new field set, replace fields in-place, refresh `strategy_version`.
- **Delete**: find row by ID, assert `status=open`, remove from list.
- **Close**: find row by ID, assert `status=open`, compute realised P&L via `pnl_engine`, set `status=closed` + `exit_dt` + `exit_price` + `realised_pnl`.

The closure pattern guarantees no lost-update across two simultaneous browser tabs / curl scripts. Phase 14 LEARNINGS already proved the kernel; Phase 19 reuses unchanged.

### D-16 — Empty-state copy

- Open trades table empty: `No open paper trades. Use the form above to record a new entry.`
- Closed trades table empty: `No closed trades yet. Trades will appear here after you close an open position.`
- Aggregate stats bar with zero closed trades: `Realised: $0.00`, `Unrealised: $0.00` (or per-open computation), `Wins: 0`, `Losses: 0`, `Win rate: —`.

## Files to modify

- `system_params.py` — bump `STATE_SCHEMA_VERSION` 5 → 6
- `state_manager.py` — add `_migrate_v5_to_v6` + register in `MIGRATIONS[6]`
- **NEW:** `pnl_engine.py` — pure-math `compute_unrealised_pnl` + `compute_realised_pnl`
- **NEW:** `web/routes/paper_trades.py` — four mutation routes + validators
- `web/app.py` — mount the new paper_trades router
- `dashboard.py` — three new render helpers (`_render_paper_trades_open`, `_render_paper_trades_closed`, `_render_paper_trades_stats`); orchestrator `_render_paper_trades_region`; plus the new HTMX entry/close form blocks; new CSS for `.stats-bar`, `.paper-trades-table`, `.row-clickable`. Modify `render_dashboard` to call `_render_paper_trades_region` and inject between the existing signal cards and the positions table.
- `tests/test_state_manager.py` — extend with `TestMigrateV5ToV6` (mirror Phase 17/22 idempotent / preserves-other / full-walk pattern)
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` — extend to walk `pnl_engine.py` against the same forbidden list as `sizing_engine.py`
- **NEW:** `tests/test_pnl_engine.py` — `TestComputeUnrealisedPnl` + `TestComputeRealisedPnl` covering LONG/SHORT × SPI/AUDUSD × edge cases (NaN last_close → NaN result, zero contracts → 0 P&L, side='LONG' with exit < entry = loss, etc.)
- **NEW:** `tests/test_web_paper_trades.py` — full route coverage: entry valid/invalid (D-04 every rule), edit valid/invalid (D-04 + 405-on-closed), delete valid/invalid (405-on-closed), close valid/invalid (D-11 P&L correctness + 405-on-closed), composite ID generation (`SPI200-20260430-001`, `SPI200-20260430-002`, `AUDUSD-20260430-001`), cookie-auth middleware enforcement
- `tests/test_dashboard.py` — extend `TestRenderDashboard*` with `TestRenderPaperTrades` (stats bar correct, open table renders unrealised P&L per row, closed table sorted by exit_dt desc, empty-state copy, sticky CSS class present)
- `tests/test_web_dashboard.py` — extend the GET `/` test to assert the three new sections render

## Out of scope (don't modify)

- `signal_engine.py` — no change. Signal logic is independent of paper trades.
- `sizing_engine.py` — no change. Sizing covers active-position contract counts; paper trades are operator-supplied.
- `notifier.py` — no change. Email body stays the v1.1 short-form; if the operator wants P&L summary in email later, that's a v1.3+ scope question.
- `data_fetcher.py` — no change.
- Auth / session machinery (`web/middleware/`) — no change. Reuses existing cookie-session middleware.
- `state.signals[]`, `state.positions[]`, `state.equity_history[]` — unchanged.

## Risk register

| Risk | Mitigation |
|------|-----------|
| Two simultaneous browser tabs assign the same trade ID | D-15 `mutate_state` `flock(LOCK_EX)` holds across read-modify-write. ID generation runs INSIDE the closure with the lock held. Test `test_concurrent_open_does_not_collide` exercises this with `multiprocessing.Process`. |
| State.json size growth from `paper_trades` array | Each row is ~300 bytes JSON. 100 trades = 30 KB. State.json size guard `test_state_json_size_under_limit` (Phase 17 risk register precedent) covers this. Operator-driven workflow caps growth. |
| LONG/SHORT P&L sign error (subtle in formula) | D-11 explicit; `tests/test_pnl_engine.py` parametrises every quadrant with hand-computed expected values. Phase 2 sizing_engine already handles SHORT correctly — same convention. |
| Closed row mutation slips through (PATCH instead of POST?) | D-12 + D-05 + 405 contract; route-layer test `test_patch_closed_row_returns_405` + `test_delete_closed_row_returns_405`. |
| `strategy_version` overwritten on edit corrupts history | D-05 documents this explicitly; toast UX surfaces it; LEDGER-02 explicitly says "matching the constant at write-time" — overwriting on edit is correct per requirement. Closed rows are immutable so post-close the version is frozen. |
| Validator drift between client (HTML form) and server | All validation is server-side per D-04. Client form has minimal HTML5 (`required`, `min="0"`) but server is the truth. Test `test_invalid_entry_returns_422_with_reason` for every D-04 rule. |
| Edit form skips D-04 validation accidentally | PATCH handler must call `_validate_open_form` identically. Test `test_edit_invalid_field_returns_422` for each rule. |
| MTM render on a missing `state.signals[<inst>]` blows up render | D-07 explicit "n/a (no close price yet)" copy; `test_mtm_with_missing_signal_renders_na`. |
| Two paper trades for the same instrument-day exhaust the 999 counter | Acceptable headroom — operator workflow is hand-driven. Test `test_id_counter_overflow_999_raises_explicit_error` so the failure mode is loud, not silent. |
| Aggregate stats bar miscounts wins/losses (zero-P&L → win? loss?) | D-06 explicit: zero is neither. `test_aggregate_stats_zero_pnl_excluded_from_wins_losses`. |

## Verification (what proves the phase shipped)

1. `python3 -c "import system_params; print(system_params.STATE_SCHEMA_VERSION)"` prints `6`.
2. Loading a v5 state.json walks forward to v6 and stamps `paper_trades: []` on the top-level state dict.
3. POST to `/paper-trade/open` with valid SPI200 LONG entry → row appears in state.json with composite ID `SPI200-<today>-001` AND `strategy_version` matching `system_params.STRATEGY_VERSION` AND `entry_cost_aud=3.0`.
4. POST to `/paper-trade/open` with `entry_dt` in the future → 422 with explicit reason.
5. POST to `/paper-trade/open` with LONG side and `stop_price > entry_price` → 422.
6. PATCH to `/paper-trade/<id>` of an open row → row updated; `strategy_version` refreshed.
7. PATCH to `/paper-trade/<id>` of a closed row → 405 with body `closed rows are immutable`.
8. DELETE on open row → row removed.
9. DELETE on closed row → 405.
10. POST to `/paper-trade/<id>/close` with valid `exit_price` → row `status=closed`, `exit_dt`/`exit_price` set, `realised_pnl` computed correctly per D-11 (verified against hand-computed value for both LONG and SHORT, both instruments).
11. Dashboard HTML at `/` contains `.stats-bar`, the open trades table with at least one row when one is open, the closed trades table sorted by `exit_dt desc`, and the close form section.
12. Stats bar values: realised + unrealised match a parallel hand-computation for a fixture state with mixed open + closed trades.
13. Empty-state copy strings (D-16) appear when both arrays are empty.
14. `pytest tests/test_pnl_engine.py tests/test_state_manager.py::TestMigrateV5ToV6 tests/test_web_paper_trades.py tests/test_dashboard.py::TestRenderPaperTrades tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` — all pass.
15. Hex-boundary: `grep -E "^import system_params|^from system_params|^import state_manager|^from state_manager|^import data_fetcher|^from data_fetcher|^import signal_engine|^from signal_engine" dashboard.py` returns ZERO matches (existing); `dashboard.py` adds `from pnl_engine import compute_unrealised_pnl` only.
16. `pnl_engine.py` forbidden-imports AST check passes (no `state_manager`/`notifier`/`dashboard`/`requests`/`datetime`/`os`).
17. Concurrent open POST test (`multiprocessing.Process`) — no ID collision.

## Deferred ideas (out of v1.2 scope)

- **Per-trade tags / free-text notes** — operator-supplied `notes: str` field for context ("entered after CPI surprise", "stop tightened to BE"). Not in LEDGER namespace; v1.3+ candidate.
- **CSV / JSON export** — operator request for `/paper-trades.csv` download. Useful for tax / record-keeping. v1.3+ candidate.
- **Filter UI for closed-trades table** — instrument filter, date-range filter, strategy_version filter (becomes useful post-v1.2 once `STRATEGY_VERSION` has actually bumped a few times). v1.3+ candidate.
- **FX-aware P&L** — convert AUDUSD P&L from USD-nominal to AUD using a daily FX rate. Currently displays USD-as-AUD per CLAUDE.md.
- **Tax-lot accounting** — average-cost vs FIFO vs specific-ID. Operator's broker handles this; paper-trade ledger doesn't replicate.
- **Real-time MTM** — live yfinance fetch on dashboard render. Rejected per D-07 (hex-boundary). Could revisit if a separate price-cache adapter is built.

## Canonical refs

- `.planning/ROADMAP.md` §Phase 19 (success criteria 1-7)
- `.planning/REQUIREMENTS.md` §LEDGER-01..06 + §VERSION-03
- `.planning/PROJECT.md` (operator + stack context)
- `SPEC.md` §v1.2+ Long-Term Roadmap (operator brainstorm 2026-04-29)
- `CLAUDE.md` — Contract specs (D-11/D-13: SPI200 $5/pt $6 RT, AUDUSD $10k $5 RT, half/half cost split per D-13)
- `.planning/phases/22-strategy-versioning-audit-trail/22-CONTEXT.md` D-04, D-05, D-09, D-10 (schema bump pattern, migration shape, hex-boundary precedent)
- `.planning/phases/17-per-signal-calculation-transparency/17-CONTEXT.md` D-08, D-09, D-10, D-12 (schema bump pattern, state-shape extension, primitives-only render, cookie-attribute precedent)
- `.planning/phases/14-trade-journal-mutation-endpoints/14-CONTEXT.md` (mutate_state lock kernel, HTMX swap pattern, route-mount pattern)
- `.planning/phases/16.1-phone-friendly-auth-ux-for-dashboard-access/16.1-CONTEXT.md` D-12, D-13 (cookie-session middleware, primitives-only render)
- `system_params.py` lines 19, 121 (constants block, `STATE_SCHEMA_VERSION` site)
- `state_manager.py` `_migrate_v3_to_v4` + `_migrate_v4_to_v5` + `MIGRATIONS` dispatch (Phase 22 + 17 precedents)
- `state_manager.py` `mutate_state` (Phase 14 D-14 lock kernel)
- `web/routes/dashboard.py` (existing GET-/ render path)
- `web/routes/positions.py` or `web/routes/trade_journal.py` (Phase 14 mutation route precedent)
- `web/middleware/auth.py` (Phase 16.1 cookie-session middleware — reused unchanged)
- `tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent` (forbidden-imports AST guard, line 762)
- `tests/test_state_manager.py::TestMigrateV4ToV5` (Phase 17 precedent — mirror exactly for V5→V6)
- `.claude/LEARNINGS.md` 2026-04-27 entry on hex-boundary primitives-only contract
- `~/.claude/LEARNINGS.md` 2026-04-29 entry on kwarg-default capture trap (apply to `STRATEGY_VERSION` access in paper-trade write site)
