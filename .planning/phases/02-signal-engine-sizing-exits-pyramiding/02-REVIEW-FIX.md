---
phase: 02-signal-engine-sizing-exits-pyramiding
fixed_at: 2026-04-21T03:30:00Z
review_path: .planning/phases/02-signal-engine-sizing-exits-pyramiding/02-REVIEW.md
iteration: 2
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-04-21T03:30:00Z
**Source review:** .planning/phases/02-signal-engine-sizing-exits-pyramiding/02-REVIEW.md
**Iteration:** 2 (pass 1 = Critical+Warning; pass 2 = Info)

**Summary:**
- Findings in scope (all severities): 5
- Fixed: 5
- Skipped: 0

## Fixed Issues

### WR-01: Falsy-Zero Bug in step() Peak/Trough Update (D-16)

**Files modified:** `sizing_engine.py`, `tests/regenerate_phase2_fixtures.py`
**Commit:** 9986550
**Applied fix:** Replaced the `or` idiom (`cur.get('peak_price') or entry_price`) with an explicit `if X is None` check in `step()` Phase 0 peak/trough update, matching the pattern already used by `get_trailing_stop` and `check_stop_hit`. The same fix was applied to the mirror in `tests/regenerate_phase2_fixtures.py` for consistency. 248 tests pass unchanged — no fixture diff produced (SPI/AUDUSD prices are far from 0.0 so the behaviour is identical for all existing fixtures).

### WR-02: Stale `position` Reference in Reversal Branch of step()

**Files modified:** `sizing_engine.py`
**Commit:** 9986550
**Applied fix:** Changed `position['direction']` to `current_position['direction']` in the reversal `elif` condition, making it consistent with all other references inside the `if current_position is not None:` block. Both WR-01 and WR-02 changes to `sizing_engine.py` were staged together and landed in the same atomic commit.

### IN-01: Redundant `new_signal != FLAT` Guard in Reversal elif

**Files modified:** `sizing_engine.py`
**Commit:** 3ff924d
**Applied fix:** Dropped the outer `new_signal != FLAT and` from the reversal `elif` clause at line 503. The guard is logically dead: the preceding `elif new_signal == FLAT:` branch already handles FLAT and sets `current_position = None`, so execution can only reach the reversal branch when `new_signal != FLAT`. The inner directional conditions already imply non-FLAT. Batched with IN-02 and IN-03 in one atomic commit.

### IN-02: Stale exit_reason Value in ClosedTrade Class Docstring

**Files modified:** `sizing_engine.py`
**Commit:** 3ff924d
**Applied fix:** Updated the `ClosedTrade` class docstring at line 65 from `'signal_exit'` (stale, does not appear in the codebase) to `'flat_signal'` (the actual value used in `_close_position` calls), matching the already-correct `_close_position` docstring. Documentation-only change; no runtime impact.

### IN-03: step() NaN Peak Update Produces Non-Finite Peak in Output Position

**Files modified:** `sizing_engine.py`
**Commit:** 3ff924d
**Applied fix:** Added a data-quality contract paragraph to the `step()` docstring (after the existing NaN guard note). The paragraph explicitly states that `step()` does NOT guard against NaN `bar['high']`/`bar['low']`, that such values will corrupt `peak_price`/`trough_price` in output position state, and that Phase 3's data-fetch/record_trade layer is responsible for supplying clean finite OHLC data before calling `step()`. Option B from the review was chosen (document the contract rather than add a guard) — consistent with the pure-math phase 2 scope.

## Skipped Issues

None — all five findings were fixed across two passes.

---

**Test suite result after all fixes:** 248 passed in 1.18s (no regressions across both passes)

**Commits:**
- Pass 1 (WR-01 + WR-02): `9986550`
- Pass 2 (IN-01 + IN-02 + IN-03): `3ff924d`

---

_Fixed: 2026-04-21T03:30:00Z_
_Fixer: Claude Sonnet 4.6 (gsd-code-fixer)_
_Iteration: 2_
