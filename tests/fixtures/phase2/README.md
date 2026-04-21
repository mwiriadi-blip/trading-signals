# Phase 2 Scenario Fixtures

15 named JSON fixtures per Phase 2 D-14: 9 signal-transition truth-table cells + 6 edge cases.
Generated offline by `tests/regenerate_phase2_fixtures.py`. Do NOT import `sizing_engine`
inside the regenerator — the recipes ARE the authoritative spec (B-4 dual-maintenance accepted).

## Schema

Each fixture has the following top-level keys:

- `description`: human-readable scenario goal (filename + this is the documentation).
- `prev_position`: Position TypedDict (or null for "no position" cells).
- `bar`: today's OHLCV `{open, high, low, close, volume}` + ISO `date`.
- `indicators`: dict of 8 indicator scalars `{atr, adx, pdi, ndi, mom1, mom3, mom12, rvol}`.
- `account`: AUD account value before this bar.
- `old_signal` / `new_signal`: previous and current signal in `{-1, 0, 1}`.
- `multiplier`: contract multiplier (`SPI_MULT=5.0` for SPI mini; `AUDUSD_NOTIONAL=10000.0` for AUD/USD).
- `instrument_cost_aud`: full round-trip cost in AUD (D-13 split: half deducted on open, half on close).
- `expected`: per-callable expected outputs:
  - `sizing_decision`: `{contracts, warning}` from `calc_position_size`, or null if no entry occurs.
  - `trail_stop`: float result of `get_trailing_stop`, or null if no open position.
  - `stop_hit`: bool result of `check_stop_hit`, or null if no open position.
  - `pyramid_decision`: `{add_contracts, new_level}` from `check_pyramid`, or null if not evaluated.
  - `unrealised_pnl`: float from `compute_unrealised_pnl` on `prev_position`, or null if no position.
  - `position_after`: Position state AFTER `step()` processes this bar — populated by plan 02-05;
    null in plan 02-04 fixtures.

## 9 Transition Cells (D-14, D-05)

Each filename encodes the truth-table cell (old_signal -> new_signal):

| Old signal | New signal | File                              | REQ covered              |
|------------|------------|-----------------------------------|--------------------------|
| LONG       | LONG       | transition_long_to_long.json      | EXIT-06/07, PYRA-02      |
| LONG       | SHORT      | transition_long_to_short.json     | EXIT-03 (two-phase)      |
| LONG       | FLAT       | transition_long_to_flat.json      | EXIT-01                  |
| SHORT      | LONG       | transition_short_to_long.json     | EXIT-04 (two-phase)      |
| SHORT      | SHORT      | transition_short_to_short.json    | EXIT-07, PYRA-02         |
| SHORT      | FLAT       | transition_short_to_flat.json     | EXIT-02                  |
| none       | LONG       | transition_none_to_long.json      | SIZE-01..05              |
| none       | SHORT      | transition_none_to_short.json     | SIZE-01..05              |
| none       | FLAT       | transition_none_to_flat.json      | (matrix completeness)    |

## 6 Edge Cases (D-14)

| File                                           | Invariant / REQ                                         |
|------------------------------------------------|---------------------------------------------------------|
| pyramid_gap_crosses_both_levels_caps_at_1.json | PYRA-05 / D-12: gap day caps at 1 add, never 2         |
| adx_drop_below_20_while_in_trade.json          | EXIT-05: ADX < 20 overrides new_signal (close always)  |
| long_trail_stop_hit_intraday_low.json          | EXIT-08: LOW <= stop (inclusive boundary)               |
| short_trail_stop_hit_intraday_high.json        | EXIT-09: HIGH >= stop (inclusive boundary)              |
| long_gap_through_stop.json                     | EXIT-08 + Pitfall 2: detection-only; fill price = Ph3  |
| n_contracts_zero_skip_warning.json             | SIZE-05: n_raw < 1 -> contracts=0 + warning            |

## B-4 Dual-Maintenance Trade-off

The regenerator (`tests/regenerate_phase2_fixtures.py`) intentionally reimplements the
sizing, trailing-stop, stop-hit, pyramid, and unrealised-PnL math INLINE without importing
`sizing_engine.py`. This mirrors the Phase 1 oracle pattern (D-04:
`tests/oracle/wilder.py` implements ATR/ADX as a pure Python loop alongside the
vectorised pandas production code).

**Why:** If the regenerator imported `sizing_engine.py` for expected values, a bug in
`sizing_engine.py` would silently propagate into both the fixtures AND the SHA256 snapshot
(plan 02-05). The SHA256 test would still pass because both sides see the same wrong math.
Having two independent implementations means a production bug shows up as a fixture mismatch
in `TestTransitions` / `TestEdgeCases`.

**Cost (accepted):** When sizing math intentionally changes (rare; locked by D-11/D-13),
the change must be made in **two places** in the same commit:
1. `sizing_engine.py` (production code)
2. `tests/regenerate_phase2_fixtures.py` (inline helpers: `_vol_scale`, `_n_contracts`,
   `_trailing_stop`, `_stop_hit`, `_pyramid_decision`, `_close_position`)

After updating both, re-run the regenerator and commit the updated JSON fixtures.

## Regeneration

```
.venv/bin/python tests/regenerate_phase2_fixtures.py
```

Idempotent: running twice produces zero `git diff`. Recipes in the regenerator are
the authoritative spec — they re-implement sizing/exit/pyramid math longhand.

To verify idempotency after any recipe change:

```
.venv/bin/python tests/regenerate_phase2_fixtures.py
git diff --stat tests/fixtures/phase2/
```

The `git diff` output must be empty (zero changed files).
