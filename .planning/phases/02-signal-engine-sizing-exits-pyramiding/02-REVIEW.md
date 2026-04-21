---
phase: 02-signal-engine-sizing-exits-pyramiding
reviewed: 2026-04-21T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - sizing_engine.py
  - system_params.py
  - tests/regenerate_phase2_fixtures.py
  - tests/test_signal_engine.py
  - tests/test_sizing_engine.py
  - tests/determinism/phase2_snapshot.json
  - tests/fixtures/phase2/*.json (15 fixture files sampled: all 15 reviewed for schema)
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-21
**Depth:** standard
**Files Reviewed:** 7 source files + 15 JSON fixtures
**Status:** issues_found

## Summary

Phase 2 implements a clean hexagonal-lite pure-math layer: `sizing_engine.py` (calc_position_size, get_trailing_stop, check_stop_hit, check_pyramid, compute_unrealised_pnl, step), `system_params.py` (constants + Position TypedDict), test suite (248 tests), and 15 JSON scenario fixtures backed by a dual-maintenance regenerator.

The architecture is well-designed. Hex-boundary enforcement is rigorous (AST blocklist, 2-space lint guard, stdlib-only constraint). NaN-pass-through policy (B-1) is consistently applied. D-15 atr-entry anchoring is correct throughout. D-12 stateless pyramid is correct. B-5 stop-level fill is correctly implemented. No security issues, no I/O leaks, no forbidden imports.

Two warnings were found: a latent falsy-zero bug in the `step()` peak/trough update and a redundant guard condition. Three info items cover a stale docstring, dead code (redundant `new_signal != FLAT` guard), and an uncovered NaN edge case in `step()`.

---

## Warnings

### WR-01: Falsy-Zero Bug in step() Peak/Trough Update (D-16)

**File:** `sizing_engine.py:457-463`
**Issue:** The peak/trough update in `step()` Phase 0 uses `or` to fall back to `entry_price`:

```python
prev_peak = current_position.get('peak_price') or current_position['entry_price']
```

If `peak_price` is `0.0` (a valid float), the `or` expression evaluates `0.0` as falsy and substitutes `entry_price` — silently discarding the real peak. This contradicts `get_trailing_stop` and `check_stop_hit` which correctly use `if peak is None` for the same fallback. For SPI 200 prices in the 7000+ range this cannot trigger in production, but the pattern is inconsistent with the rest of the module and is a landmine if the same `step()` code is ever reused with AUDUSD prices (which are also far from 0.0, but the principle holds). The same bug exists in the regenerator mirror at `tests/regenerate_phase2_fixtures.py:212-215`.

**Fix:** Replace the `or` idiom with an explicit `None` check, matching `get_trailing_stop`/`check_stop_hit`:

```python
# sizing_engine.py:457
prev_peak = current_position['peak_price']
if prev_peak is None:
    prev_peak = current_position['entry_price']
current_position['peak_price'] = max(prev_peak, bar['high'])

# sizing_engine.py:460-463
prev_trough = current_position['trough_price']
if prev_trough is None:
    prev_trough = current_position['entry_price']
current_position['trough_price'] = min(prev_trough, bar['low'])
```

Apply the same fix to `tests/regenerate_phase2_fixtures.py:212-215`. After the fix, re-run `tests/regenerate_phase2_fixtures.py` (output will be identical for SPI/AUDUSD values — no fixture diff expected) and verify the SHA256 snapshot is unchanged.

---

### WR-02: Stale `position` Reference in Reversal Branch of step()

**File:** `sizing_engine.py:502-503`
**Issue:** In the reversal detection branch, the condition reads `position['direction']` (the original input argument) rather than `current_position['direction']` (the working copy updated in Phase 0):

```python
elif new_signal != FLAT and (
  (position['direction'] == 'LONG' and new_signal == SHORT)   # uses `position`, not `current_position`
  or (position['direction'] == 'SHORT' and new_signal == LONG)
):
```

In Phase 2 this is harmless — `position` and `current_position` share the same `direction` value (the shallow copy in Phase 0 does not change `direction`). However, it is a latent inconsistency: if Phase 4 or Phase 5 ever mutates `current_position['direction']` before reaching this branch (which would be a design error, but still), this check would silently use stale data. All other references within the `if current_position is not None:` block correctly use `current_position`.

**Fix:**
```python
elif (
  (current_position['direction'] == 'LONG' and new_signal == SHORT)
  or (current_position['direction'] == 'SHORT' and new_signal == LONG)
):
```

The `elif new_signal != FLAT and (...)` outer guard is also redundant (see IN-01).

---

## Info

### IN-01: Redundant `new_signal != FLAT` Guard in Reversal elif

**File:** `sizing_engine.py:501`
**Issue:** The reversal `elif` clause starts with `new_signal != FLAT and (...)`. This guard is logically redundant: the preceding `elif new_signal == FLAT:` branch already exits `current_position = None`, so execution can only reach line 501 when `new_signal != FLAT`. The inner conditions `(LONG and SHORT) or (SHORT and LONG)` already imply `new_signal != FLAT` since SHORT and LONG are both non-FLAT. The extra guard adds noise without adding correctness.

**Fix:** Drop the outer `new_signal != FLAT and` guard:
```python
elif (
  (current_position['direction'] == 'LONG' and new_signal == SHORT)
  or (current_position['direction'] == 'SHORT' and new_signal == LONG)
):
```

---

### IN-02: Stale exit_reason Value in ClosedTrade Class Docstring

**File:** `sizing_engine.py:65`
**Issue:** The `ClosedTrade` class docstring lists the valid exit reasons as:

```
exit_reason: one of 'signal_exit', 'signal_reversal', 'stop_hit', 'adx_exit'
```

But `step()` uses `'flat_signal'` (not `'signal_exit'`) when closing on a FLAT signal (line 497). The `_close_position` docstring at line 626 correctly lists `'flat_signal'`. The class-level docstring is stale — `'signal_exit'` does not appear anywhere in the codebase except this docstring.

This is a documentation-only discrepancy (no runtime impact), but since `ClosedTrade.exit_reason` is an untyped `str` field, Phase 3 or Phase 4 code that pattern-matches on `exit_reason` values could be misled by this docstring.

**Fix:** Update line 65:
```python
exit_reason: one of 'flat_signal', 'signal_reversal', 'stop_hit', 'adx_exit'
```

---

### IN-03: step() NaN Peak Update Produces Non-Finite Peak in Output Position

**File:** `sizing_engine.py:458`
**Issue:** If `bar['high']` is NaN (upstream data gap), the Phase 0 peak update:

```python
current_position['peak_price'] = max(prev_peak, bar['high'])
```

`max(finite, nan)` in Python returns `nan` — so `peak_price` becomes NaN on the output position. On the next bar, `get_trailing_stop` will then return NaN (B-1 rule fires on `atr_entry` not `peak_price`, so it won't catch this), and `check_stop_hit` will return False (correct per B-1 but the NaN peak is now persisted in state). The `step()` docstring mentions a NaN guard for ADX but does not document this path.

This is distinct from B-1 (which documents NaN atr_entry behaviour). A NaN bar `high` is a plausible upstream data quality event. The same issue applies to `bar['low']` for SHORT trough updates.

There is currently no test for `bar['high']=NaN` or `bar['low']=NaN` passed into `step()`.

**Fix (two options):**

Option A — Guard in step() Phase 0:
```python
if math.isfinite(bar['high']):
    current_position['peak_price'] = max(prev_peak, bar['high'])
# else: keep prev_peak unchanged (no update on missing data)
```

Option B — Document as a known gap in the docstring with a `# TODO: Phase 3/4 guard` note, since Phase 3 will own data-quality filtering before calling `step()`.

Option B is acceptable given the phase 2 pure-math scope. If choosing Option B, add a comment to `step()` near line 458 explicitly noting that NaN `bar['high']`/`bar['low']` will corrupt `peak_price`/`trough_price` state, and that Phase 3 is responsible for ensuring clean OHLC data before calling `step()`.

---

## Fixture Schema Sanity

All 15 JSON fixtures share a consistent 10-key top-level schema:
`account`, `bar`, `description`, `expected`, `indicators`, `instrument_cost_aud`, `multiplier`, `new_signal`, `old_signal`, `prev_position`.

All fixtures set `allow_nan=False` (null for None, no raw NaN in JSON). `sort_keys=True` applied consistently. The `expected` dict in all 15 fixtures contains the same 6 keys: `position_after`, `pyramid_decision`, `sizing_decision`, `stop_hit`, `trail_stop`, `unrealised_pnl`. Schema is consistent across all 15 fixtures.

The `phase2_snapshot.json` contains exactly 15 SHA256 entries, one per fixture. The hash generation in `test_phase2_snapshot_hash_stable` uses `sort_keys=True, separators=(',', ':')` which is deterministic across Python runs — the snapshot will be stable.

---

_Reviewed: 2026-04-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
