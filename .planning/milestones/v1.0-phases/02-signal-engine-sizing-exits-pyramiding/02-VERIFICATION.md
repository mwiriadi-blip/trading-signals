---
phase: 02-signal-engine-sizing-exits-pyramiding
verified: 2026-04-21T00:00:00+08:00
status: passed
score: 5/5 must-haves verified
must_haves_verified: 5/5
requirements_traced: 20/20
success_criteria_proven: 5/5
overrides_applied: 0
---

# Phase 2: Signal Engine — Sizing, Exits, Pyramiding Verification Report

**Phase Goal:** Produce deterministic position sizes, exit decisions, and pyramid-level transitions for any given (state, indicators, today's bar) input — pure functions, fixture-tested, with the 9-cell signal-transition truth table locked down.

**Verified:** 2026-04-21T00:00:00+08:00
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `n_contracts == 0` after vol-scale clip returns a skip-trade decision with a "size=0" warning string, no `max(1, …)` floor applied | VERIFIED | `calc_position_size` in `sizing_engine.py` uses `int(n_raw)` with no `max(1, ...)` guard (grep returns 0 matches for `max(1`). `TestSizing::test_no_max_one_floor_when_undersized` (atr=80, n_raw=0.667 → contracts=0, warning starts with `size=0:`) passes. `TestSizing::test_zero_contracts_warning_format` asserts 6 diagnostic substrings in the warning. `n_contracts_zero_skip_warning` fixture SHA256-locked in `phase2_snapshot.json`. |
| 2 | The full 9-cell signal-transition matrix produces the right exit-then-entry sequence — LONG→FLAT closes, LONG→SHORT closes then reopens SHORT in one run | VERIFIED | All 27 tests in `TestTransitions` pass (18 parametrized individual-callable tests + 9 named per-cell tests). Manual `step()` trace on `transition_long_to_short` fixture confirms: `closed_trade.exit_reason == 'signal_reversal'` + `sizing_decision.contracts == 0` (SHORT n_raw=0.73 rounds to 0 per SIZE-01/04; the reversal sequence itself fires). `transition_short_to_long` confirms `closed_trade.direction == 'SHORT'` and `sizing_decision` is populated (entry attempted). `TestStep::test_step_position_after_matches_fixture` parametrized over all 9 transition fixtures passes. All 15 fixtures SHA256-locked via `test_phase2_snapshot_hash_stable`. |
| 3 | Trailing stop updates peak with today's HIGH (LONG) and trough with today's LOW (SHORT); stop hits when today's LOW ≤ LONG stop or today's HIGH ≥ SHORT stop | VERIFIED | `sizing_engine.py` step() Phase 0 (D-16) updates `peak_price = max(prev_peak, bar['high'])` and `trough_price = min(prev_trough, bar['low'])` via shallow copy BEFORE exit logic. `long_trail_stop_hit_intraday_low` fixture: peak=7050, atr_entry=53, stop=6891, bar.low=6890 → `check_stop_hit` returns `True`. Manual trace confirms `stop == 6891.0` and `hit == True`. `TestExits` (14 tests) covers EXIT-06/07/08/09 including both boundary-exact and strict-below/above cases. `TestStep::test_step_d16_updates_peak_on_copy_not_input` asserts input position is NOT mutated. |
| 4 | Given a gap-up fixture crossing both +1×ATR and +2×ATR in one bar, pyramid level advances by exactly 1 (not 2), and never exceeds level 2 (3 total contracts) | VERIFIED | `pyramid_gap_crosses_both_levels_caps_at_1` fixture: `expected.pyramid_decision == {add_contracts: 1, new_level: 1}`, `expected.position_after.n_contracts == 3`, `expected.position_after.pyramid_level == 1`. `check_pyramid` in `sizing_engine.py` evaluates ONLY `(level + 1) * atr_entry` threshold — a single call can never return `add_contracts=2` (grep confirms `add_contracts=2` returns 0 matches). `TestEdgeCases::test_pyramid_gap_crosses_both_levels_caps_at_1` and `TestStep::test_step_d18_pyramid_add_applied_to_position_after` both pass. `TestPyramid::test_pyramid_gap_day_caps_at_one_add_long/short` passes. |
| 5 | ADX < 20 while in an active position produces an immediate-close decision regardless of trailing-stop state | VERIFIED | `step()` Phase 1 checks `math.isfinite(adx) and adx < ADX_EXIT_GATE` BEFORE stop-hit check. `adx_drop_below_20_while_in_trade` fixture: ADX=18, new_signal=LONG (signal would normally hold), `expected.position_after == null`. `TestEdgeCases::test_adx_drop_below_20_while_in_trade` asserts `fix['indicators']['adx'] < ADX_EXIT_GATE`. `TestStep::test_step_no_entry_on_adx_exit_day` asserts `result.closed_trade.exit_reason == 'adx_exit'` and `result.position_after is None` even when new_signal=LONG. Both pass. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sizing_engine.py` | All 6 public functions implemented; no NotImplementedError remaining | VERIFIED | All 6 callables (`calc_position_size`, `get_trailing_stop`, `check_stop_hit`, `check_pyramid`, `compute_unrealised_pnl`, `step`) fully implemented. `grep -c NotImplementedError sizing_engine.py` returns 0. 651 lines. |
| `system_params.py` | SPI_MULT=5.0, SPI_COST_AUD=6.0, Position TypedDict, all Phase 2 constants | VERIFIED | `SPI_MULT: float = 5.0`, `SPI_COST_AUD: float = 6.0`, `RISK_PCT_LONG=0.01`, `RISK_PCT_SHORT=0.005`, `TRAIL_MULT_LONG=3.0`, `TRAIL_MULT_SHORT=2.0`, `ADX_EXIT_GATE=20.0`, `MAX_PYRAMID_LEVEL=2`. `Position` TypedDict with all 8 fields. |
| `tests/test_sizing_engine.py` | TestSizing, TestExits, TestPyramid, TestTransitions, TestEdgeCases, TestStep all populated | VERIFIED | All 6 test classes populated; 248 total tests pass (0 failures, 0 skips). |
| `tests/determinism/phase2_snapshot.json` | 15 SHA256 hashes | VERIFIED | 15 entries confirmed. `test_phase2_snapshot_hash_stable` parametrized over all 15 fixtures — all 15 pass. |
| `tests/fixtures/phase2/` | 15 JSON fixture files (9 transitions + 6 edge cases) | VERIFIED | Exactly 15 JSON files present plus README.md. All match D-14 names. |
| `tests/regenerate_phase2_fixtures.py` | Offline idempotent regenerator with `[regen-p2]` log prefix | VERIFIED | File exists; contains `[regen-p2]` prefix and `allow_nan=False`. Imports nothing from `sizing_engine` (B-4 dual-maintenance). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `sizing_engine.calc_position_size` | `system_params.{RISK_PCT_LONG, RISK_PCT_SHORT, TRAIL_MULT_LONG, TRAIL_MULT_SHORT, VOL_SCALE_*}` | Named constant imports; `_vol_scale` helper | WIRED | All 7 constants used by name. `_vol_scale` extracted as private helper. 0 hardcoded literals. |
| `sizing_engine.compute_unrealised_pnl` | `cost_aud_open` explicit parameter (D-17) | `cost_aud_open: float` parameter | WIRED | `inspect.signature(compute_unrealised_pnl).parameters` contains `cost_aud_open`. `TestSizing::test_unrealised_pnl_signature_has_cost_aud_open` and `TestDeterminism::test_sizing_engine_has_core_public_surface` both pin this. |
| `sizing_engine.get_trailing_stop / check_stop_hit` | `position['atr_entry']` (D-15 anchor, NOT today's atr) | `del atr` at function start; use `atr_entry = position['atr_entry']` | WIRED | `grep -c 'del atr' sizing_engine.py` returns 2 (one in each function). `TRAIL_MULT_LONG * atr_entry` pattern confirmed in both. |
| `sizing_engine.step` | `calc_position_size + get_trailing_stop + check_stop_hit + check_pyramid + compute_unrealised_pnl` | Sequential call chain in 5 phases | WIRED | Step calls all 5 subfunctions. D-16 peak/trough update Phase 0 confirmed. D-18 pyramid apply via dict spread `'pyramid_level': pyramid_decision.new_level` confirmed. D-19 INPUT account confirmed (no account mutation). |
| `TestTransitions / TestEdgeCases / TestStep` | `tests/fixtures/phase2/*.json` | `_load_phase2_fixture(name)` helper | WIRED | All 15 fixture names appear in `TRANSITION_FIXTURES` + `EDGE_CASE_FIXTURES` + `ALL_PHASE2_FIXTURES` module-level lists. `_load_phase2_fixture` confirmed in test file. |
| `TestDeterminism::test_phase2_snapshot_hash_stable` | `tests/determinism/phase2_snapshot.json` | `hashlib.sha256(json.dumps(..., sort_keys=True, separators=...))` | WIRED | `PHASE2_SNAPSHOT_PATH` constant in `test_signal_engine.py`. 15/15 parametrized cases pass. |

### Data-Flow Trace (Level 4)

Not applicable. Phase 2 is a pure-math stdlib module with no persistent state, no I/O, and no dynamic rendering. All data flows are scalar-in / dataclass-out, fully exercised by the fixture-driven test suite.

### Behavioral Spot-Checks

| Behavior | Result | Status |
|----------|--------|--------|
| Full test suite (248 tests) exits 0 | 248 passed in 1.43s | PASS |
| Phase 1 regression (103 tests in `test_signal_engine.py`) | 103 passed, 0 failures | PASS |
| `test_phase2_snapshot_hash_stable` parametrized over 15 fixtures | 15/15 passed | PASS |
| AST guard `test_phase2_hex_modules_no_numpy_pandas` | 2/2 passed (sizing_engine + system_params) | PASS |
| Ruff clean on `sizing_engine.py`, `system_params.py`, `tests/test_sizing_engine.py` | All checks passed | PASS |
| Manual `step()` trace — LONG→SHORT reversal: `closed_trade.exit_reason == 'signal_reversal'` and `sizing_decision` populated | Confirmed | PASS |
| Manual `get_trailing_stop` trace — LONG peak=7050, atr_entry=53 → stop=6891; bar.low=6890 → `check_stop_hit` True | Confirmed | PASS |
| `grep -cF 'add_contracts=2' sizing_engine.py` returns 0 (D-12) | 0 | PASS |
| `grep -cF 'max(1' sizing_engine.py` returns 0 (no floor, operator-locked) | 0 | PASS |
| `grep -c 'del atr' sizing_engine.py` returns 2 (D-15 entry-ATR anchor) | 2 | PASS |

### Requirements Coverage

| Requirement | Plan | Description | Status | Evidence |
|-------------|------|-------------|--------|----------|
| SIZE-01 | 02-02 | risk_pct = 1.0% LONG, 0.5% SHORT | SATISFIED | `RISK_PCT_LONG=0.01`, `RISK_PCT_SHORT=0.005` in system_params; `test_risk_pct_long_is_1pct` + `test_risk_pct_short_is_half_pct` pass |
| SIZE-02 | 02-02 | trail_mult = 3.0 LONG, 2.0 SHORT | SATISFIED | `TRAIL_MULT_LONG=3.0`, `TRAIL_MULT_SHORT=2.0` in system_params; `test_trail_mult_by_direction` passes |
| SIZE-03 | 02-02 | vol_scale = clip(0.12/RVol, 0.3, 2.0); NaN/zero guard | SATISFIED | `_vol_scale` helper in sizing_engine; `test_vol_scale_clip_ceiling/floor/nan_guard/zero_guard` all pass |
| SIZE-04 | 02-02 | n_contracts = int(n_raw); no max(1) floor | SATISFIED | `int(n_raw)` with no floor; `grep -cF 'max(1'` returns 0; `test_no_max_one_floor_when_undersized` passes |
| SIZE-05 | 02-02, 02-04 | n_contracts==0 → skip + "size=0" warning | SATISFIED | Warning starts with `size=0:` with 6 diagnostic substrings; `test_zero_contracts_warning_format` + `n_contracts_zero_skip_warning` fixture pass |
| SIZE-06 | 02-01, 02-02 | SPI mini $5/pt, $6 AUD RT; AUD/USD $10k notional, $5 AUD RT (operator D-11 override; REQUIREMENTS.md wording is stale at $25/pt) | SATISFIED | `SPI_MULT=5.0` confirmed; `test_contract_specs_spi_mini` asserts `SPI_MULT==5.0`; SPEC.md §6 updated to $5/pt in 02-01 |
| EXIT-01 | 02-03, 02-05 | LONG→FLAT closes the open LONG | SATISFIED | `step()` `new_signal == FLAT` branch closes via `_close_position`; `test_transition_long_to_flat` passes |
| EXIT-02 | 02-03, 02-05 | SHORT→FLAT closes the open SHORT | SATISFIED | Same FLAT branch; `test_transition_short_to_flat` passes |
| EXIT-03 | 02-05 | LONG→SHORT closes LONG then opens SHORT in one run | SATISFIED | Reversal branch in `step()` closes first then sizes; `test_transition_long_to_short` passes; manual trace confirmed |
| EXIT-04 | 02-05 | SHORT→LONG closes SHORT then opens LONG | SATISFIED | Same reversal branch; `test_transition_short_to_long` passes; `test_step_d19_reversal_uses_input_account` passes |
| EXIT-05 | 02-05 | ADX < 20 closes position immediately | SATISFIED | `step()` Phase 1 checks `adx < ADX_EXIT_GATE` first; `test_step_no_entry_on_adx_exit_day` passes |
| EXIT-06 | 02-03 | LONG trailing stop = peak − 3×ATR_entry | SATISFIED | `get_trailing_stop` LONG branch: `peak - TRAIL_MULT_LONG * atr_entry`; D-15 anchor to `atr_entry` not today's atr; tests pass |
| EXIT-07 | 02-03 | SHORT trailing stop = trough + 2×ATR_entry | SATISFIED | `get_trailing_stop` SHORT branch: `trough + TRAIL_MULT_SHORT * atr_entry`; tests pass |
| EXIT-08 | 02-03 | LONG stop hit if today's LOW ≤ stop | SATISFIED | `check_stop_hit` LONG: `return low <= stop`; `test_long_stop_hit_intraday_low_at_boundary` + `test_long_stop_hit_intraday_low_below` pass |
| EXIT-09 | 02-03 | SHORT stop hit if today's HIGH ≥ stop | SATISFIED | `check_stop_hit` SHORT: `return high >= stop`; `test_short_stop_hit_intraday_high_at_boundary` passes |
| PYRA-01 | 02-01, 02-05 | Pyramid level persists in state per position | SATISFIED | `pyramid_level` field in `Position` TypedDict; `step()` D-18 applies `pyramid_decision.new_level` to `position_after`; `test_position_carries_pyramid_level` passes |
| PYRA-02 | 02-03 | At level 0, adds 1 contract when unrealised ≥ 1×ATR_entry → level 1 | SATISFIED | `check_pyramid` level 0 branch: threshold = `1 * atr_entry`; `test_pyramid_level_0_to_1_long/short` pass |
| PYRA-03 | 02-03 | At level 1, adds 1 contract when unrealised ≥ 2×ATR_entry → level 2 | SATISFIED | `check_pyramid` level 1 branch: threshold = `2 * atr_entry`; `test_pyramid_level_1_to_2_long/short` pass |
| PYRA-04 | 02-03 | Never adds beyond 3 total contracts (level ≤ 2) | SATISFIED | `if level >= MAX_PYRAMID_LEVEL: return PyramidDecision(0, level)`; `test_pyramid_capped_at_level_2` passes |
| PYRA-05 | 02-03, 02-04 | Maximum one pyramid step per daily run | SATISFIED | Stateless D-12 enforcement: evaluates only current-level trigger; `test_pyramid_gap_crosses_both_levels_caps_at_1` + fixture `pyramid_gap_crosses_both_levels_caps_at_1` confirm `add_contracts=1` on gap day |

**Requirements coverage: 20/20**

Note on SIZE-06: `REQUIREMENTS.md` body text says "$25/point, $30 AUD round-trip" which is stale. D-11 (operator-locked, confirmed at discuss-phase 2) overrides to SPI mini $5/pt, $6 AUD RT. `SPEC.md` §6 was amended in plan 02-01 to reflect this. `system_params.py` (`SPI_MULT=5.0`, `SPI_COST_AUD=6.0`) and the test suite (`test_contract_specs_spi_mini` asserts `SPI_MULT==5.0`) are canonical. The REQUIREMENTS.md traceability table is also stale (shows SIZE-01..05, EXIT-06..09, PYRA-01..04 as "Pending") — all 20 requirements are fully implemented and tested as of Phase 2 completion.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None found | — | — | — |

Scan confirmed:
- 0 `NotImplementedError` in `sizing_engine.py`
- 0 `TODO/FIXME/PLACEHOLDER` in phase 2 files
- 0 `max(1, ...)` floor (operator-locked)
- 0 `add_contracts=2` (D-12 stateless cap enforced)
- Ruff clean on all 3 primary files

### Decision Verification (D-07 through D-19)

| Decision | Check | Status |
|----------|-------|--------|
| D-07: sizing_engine.py + system_params.py exist; AST blocklist enforces no I/O imports | `test_phase2_hex_modules_no_numpy_pandas` 2/2 pass; `test_forbidden_imports_absent` passes | VERIFIED |
| D-11: SPI_MULT=5.0, SPI_COST_AUD=6.0 | Confirmed in system_params.py lines 62-63 | VERIFIED |
| D-12: `add_contracts=2` never appears | `grep -cF 'add_contracts=2' sizing_engine.py` returns 0 | VERIFIED |
| D-15: stop distance anchored to position['atr_entry'] | `del atr` in get_trailing_stop + check_stop_hit; `grep -c 'del atr'` returns 2 | VERIFIED |
| D-16: step() updates peak/trough on shallow copy before exit logic | `current_position = dict(position)` then `peak_price = max(...)` / `trough_price = min(...)` at Phase 0; `test_step_d16_updates_peak_on_copy_not_input` passes | VERIFIED |
| D-17: step() and compute_unrealised_pnl signatures include explicit parameters | `cost_aud_open` in `compute_unrealised_pnl` signature; `account, multiplier, cost_aud_open` in `step()` signature; `test_step_d17_signature` + `test_unrealised_pnl_signature_has_cost_aud_open` pass | VERIFIED |
| D-18: step() applies pyramid add to position_after | `position_after = {**position_after, 'n_contracts': ..., 'pyramid_level': pyramid_decision.new_level}` at line 576-580; `test_step_d18_pyramid_add_applied_to_position_after` passes | VERIFIED |
| D-19: Reversal sizing uses input account | `account` is pass-through input parameter; no mutation in step(); `test_step_d19_reversal_uses_input_account` passes | VERIFIED |

### Human Verification Required

None. Phase 2 is a pure-math stdlib module. All observable behaviors are verifiable programmatically via the fixture-driven test suite. 248 tests pass with 0 failures.

### Gaps Summary

No gaps found. All 5 ROADMAP success criteria are proven by named passing tests. All 20 requirements (SIZE-01..06, EXIT-01..09, PYRA-01..05) are traced to implementations and covered by at least one passing named test. The determinism oracle (15 SHA256 hashes in `phase2_snapshot.json`) locks all fixture goldens against drift. Phase 1 regression test suite (103 tests) passes with 0 failures.

The only non-blocking observation is that `REQUIREMENTS.md` has stale status entries ("Pending" for requirements completed in Phase 2) and a stale SIZE-06 body text ($25/pt vs the operator-overridden $5/pt). These are doc artifacts that do not affect code correctness; they should be updated when the REQUIREMENTS.md is next touched.

---

_Verified: 2026-04-21T00:00:00+08:00_
_Verifier: Claude (gsd-verifier)_
