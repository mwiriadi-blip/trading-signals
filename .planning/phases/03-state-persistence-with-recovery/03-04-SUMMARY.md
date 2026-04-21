---
phase: 03-state-persistence-with-recovery
plan: 04
subsystem: state-persistence
tags:
  - state-persistence
  - record-trade
  - equity-history
  - d-19-extended-validation
  - d-20-no-mutation
  - b-4-equity-boundary-validation
  - phase-4-boundary-ac
  - phase-gate
dependency_graph:
  requires:
    - 03-01 (state_manager I/O hex scaffold; _REQUIRED_TRADE_FIELDS frozenset; Position TypedDict)
    - 03-02 (_atomic_write D-17; _migrate; save_state; load_state happy+missing-file)
    - 03-03 (reset_state; append_warning B-5; _backup_corrupt B-1+B-2; _validate_loaded_state D-18; load_state corruption+happy-path full composition)
  provides:
    - _validate_trade (D-15 + D-19 extended — all 11 required trade fields validated with ValueError messages naming the offending field)
    - record_trade (D-13 atomic position close + D-14 closing-half cost split + D-15/D-19 validation guard + D-16 not-idempotent + D-20 non-mutating trade_log append)
    - update_equity_history (D-04 caller-computed equity append + B-4 boundary validation — date shape + equity finiteness)
    - import math (alphabetical, between json and os) — needed for D-19 numeric-field finiteness + B-4 equity finiteness checks
    - TestRecordTrade (15 tests — 7 base D-15 + 6 D-19 extended + 1 D-20 no-mutation + 1 CRITICAL Phase 4 boundary)
    - TestEquityHistory (6 tests — 3 STATE-06 happy path + 3 B-4 validation)
  affects:
    - Phase 4 orchestrator (MUST compute gross_pnl = RAW price-delta and pass THAT to record_trade; MUST NOT pass ClosedTrade.realised_pnl; can safely reuse trade dict after record_trade per D-20; must pass ISO YYYY-MM-DD date str and finite equity float to update_equity_history or handle ValueError)
    - `/gsd-verify-work 3` (reads this SUMMARY + the plan to confirm Phase 3 goal achievement)
tech-stack:
  added: []
  patterns:
    - "_REQUIRED_TRADE_FIELDS frozenset - set difference guard for missing-field detection (O(1) set-difference producing a sorted list for deterministic test assertions)"
    - "D-15 + D-19 validation: enum checks for instrument/direction, int>0 rejecting bool for n_contracts, non-empty str loop for date/reason fields, finite numeric loop rejecting bool/NaN/inf via math.isfinite for price/pnl/multiplier/cost fields"
    - "D-20 non-mutating append: `state['trade_log'].append(dict(trade, net_pnl=net_pnl))` — shallow copy of caller's trade dict with net_pnl added; caller's dict unchanged after the call"
    - "D-14 closing-half cost: `closing_cost_half = cost_aud * n_contracts / 2`; `net_pnl = gross_pnl - closing_cost_half`; Phase 2 deducts opening-half in compute_unrealised_pnl, Phase 3 deducts closing-half here — the split together sums to the full round-trip cost"
    - "B-4 boundary validation at update_equity_history: date shape check (isinstance str + len==10) + equity finiteness (isinstance int|float + not bool + math.isfinite) — catches Phase 4 wire-up bugs immediately at the boundary rather than waiting for save_state's allow_nan=False later"
    - "CRITICAL Phase 4 boundary encoded as a named test with worked numerical example (CORRECT account=100_994.0 vs BUG account=100_988.0; delta = closing_cost_half = 6.0) — any Phase 4 PR that confuses ClosedTrade.realised_pnl with gross_pnl fails this test loudly"
    - "PEP 604 union syntax (int | float) in isinstance — ruff UP038 auto-fix from (int, float) tuple pattern; semantically equivalent and Python 3.10+ preferred form"
key-files:
  created:
    - .planning/phases/03-state-persistence-with-recovery/03-04-SUMMARY.md
  modified:
    - state_manager.py (3 NotImplementedError stubs replaced with full implementations; `import math` added; zero stubs remain — PHASE GATE)
    - tests/test_state_manager.py (TestRecordTrade + TestEquityHistory populated; 21 new test methods across the two classes)
decisions:
  - "Rule 3 ruff UP038 auto-fix: `isinstance(value, (int, float))` and `isinstance(equity, (int, float))` converted to `isinstance(value, int | float)` and `isinstance(equity, int | float)` per PEP 604. Both forms reject bool identically (isinstance(True, int|float) is True, exactly like the tuple form) and the subsequent `isinstance(value, bool)` check still fires. Plan AC greps still hit because the updated syntax matches the function-body intent; no AC grep specifically requires the tuple form."
  - "Task 1 verify step intentionally hits empty TestRecordTrade/TestEquityHistory classes (they still had `pass` bodies at commit time) — pytest collects 0 tests and returns exit 5. The Task 1→Task 2 commit ordering is implementation-first, tests-second, matching the plan's structure. The real verification for both tasks is Task 2's full-suite run after tests are populated. No deviation."
  - "D-20 no-mutation test uses double-quoted strings for assertion messages that contain apostrophes (caller's trade dict) to avoid backslash-escape noise; plan had escaped apostrophes (caller\\'s) which would have produced literal backslash characters in the assertion message. Functional behavior identical; assertion messages are cleaner."
  - "CRITICAL Phase 4 boundary test `test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl` kept verbatim per quality gate — CORRECT path proves account=100_994.0; BUG path (passing realised_pnl as gross_pnl) proves account=100_988.0; delta assertion proves the bug magnitude equals closing_cost_half exactly. If Phase 4's orchestrator misuses the boundary, this test fails loudly with a $6 discrepancy per trade."
metrics:
  duration_minutes: ~15
  completed: 2026-04-21
  tasks_total: 2
  tasks_completed: 2
  files_created: 0 (SUMMARY.md is planning artifact, not code)
  files_modified: 2
  tests_before: 273
  tests_after: 294
  new_tests: 21
  stub_count_before: 3
  stub_count_after: 0
---

# Phase 3 Plan 04: Wave 3 (PHASE GATE) — Trade Recording + Equity History Summary

Wave 3 closes Phase 3: three NotImplementedError stubs filled (`_validate_trade`, `record_trade`, `update_equity_history`), two test classes populated with 21 new methods, `import math` added to state_manager.py, zero stubs remain. Two commits, 294/294 tests passing, Phase 3 ships.

## One-liner

record_trade + update_equity_history implemented with D-15/D-19 full-field validation, D-14 closing-half cost split, D-20 non-mutating trade_log append, B-4 equity-boundary validation, and a CRITICAL Phase 4 boundary AC test proving the $6/trade double-counting bug path.

## Performance

- **Duration:** ~15 minutes
- **Started:** 2026-04-21 (Wave 3)
- **Completed:** 2026-04-21
- **Tasks:** 2/2
- **Files modified:** 2 (state_manager.py, tests/test_state_manager.py)

## Functions Implemented

### `_validate_trade(trade: dict) -> None`  (D-15 + D-19)

- **D-15 (base):** `missing = _REQUIRED_TRADE_FIELDS - trade.keys()` set-difference guard naming missing field(s) via ValueError; instrument enum `{SPI200, AUDUSD}`; direction enum `{LONG, SHORT}`; n_contracts `isinstance(int) and not isinstance(bool) and > 0`.
- **D-19 (extended):** string-field loop for `entry_date`, `exit_date`, `exit_reason` (non-empty str); numeric-field loop for `entry_price`, `exit_price`, `gross_pnl`, `multiplier`, `cost_aud` (`isinstance(int|float)` + `not isinstance(bool)` + `math.isfinite`).
- **Error messages name the offending field** via f-string so Phase 4 wire-up bugs surface immediately with a specific failure point.

### `record_trade(state, trade) -> dict`  (D-13/D-14/D-15/D-16/D-20)

- Calls `_validate_trade(trade)` first — raises ValueError on bad input before any mutation.
- **D-14 closing-half cost:** `closing_cost_half = trade['cost_aud'] * trade['n_contracts'] / 2`; `net_pnl = trade['gross_pnl'] - closing_cost_half`. Phase 2 already deducted opening-half via `compute_unrealised_pnl`; this is the closing-half. Sum matches full round-trip cost.
- **D-13 atomic mutation:** `state['account'] += net_pnl`; `state['trade_log'].append(dict(trade, net_pnl=net_pnl))`; `state['positions'][trade['instrument']] = None`.
- **D-20 non-mutating append:** uses `dict(trade, net_pnl=net_pnl)` — a shallow copy of the caller's trade dict with `net_pnl` added. The caller's `trade` dict is **unchanged** after the call. Phase 4 can safely reuse the trade dict for logging, metrics, etc. without worrying about record_trade silently adding keys.
- **D-16 not-idempotent:** caller must call exactly once per closed trade. Documented in docstring.
- **CRITICAL Phase 4 boundary preserved verbatim in docstring:** `trade['gross_pnl']` MUST be RAW price-delta P&L, NOT Phase 2's `ClosedTrade.realised_pnl`. Double-counting the closing cost is the failure mode.

### `update_equity_history(state, date, equity) -> dict`  (STATE-06 + D-04 + B-4)

- **D-04:** `equity` is caller-computed. state_manager does NOT import sizing_engine — Phase 4 orchestrator computes `equity = state['account'] + sum(unrealised_pnl across active positions)` and passes the total.
- **B-4 boundary validation:**
  - `date`: `isinstance(str)` and `len == 10` (ISO YYYY-MM-DD shape; not a full regex match).
  - `equity`: `isinstance(int | float)` and `not isinstance(bool)` and `math.isfinite(equity)`.
  - Raises `ValueError` with parameter-named message on malformed input.
- Then appends `{'date': date, 'equity': equity}` to `state['equity_history']`. Returns mutated state for chain-friendly use.

## Import Added

- `import math` — alphabetical position between `import json` and `import os`. Needed by `_validate_trade` (D-19 `math.isfinite`) and `update_equity_history` (B-4 `math.isfinite`). `math` is stdlib; AST blocklist for state_manager.py permits stdlib + system_params, so no AST-guard update was required.

## Tests Added (21 methods, 2 classes)

### `TestRecordTrade` (15 tests)

| # | Test | Proves |
|---|------|--------|
| 1 | `test_record_trade_adjusts_account_by_net_pnl` | D-14: cost_aud=6, n_contracts=2, gross_pnl=1000 → net_pnl=994 → account=100_994.0 |
| 2 | `test_record_trade_appends_to_trade_log_with_net_pnl` | STATE-05/D-13/D-20: trade_log entry has net_pnl=994; original gross_pnl preserved |
| 3 | `test_record_trade_sets_position_to_none` | D-01/D-13: positions[instrument] = None after close; other instrument untouched |
| 4 | `test_record_trade_raises_on_missing_field` | D-15: ValueError naming missing field |
| 5 | `test_record_trade_raises_on_invalid_instrument` | D-15: instrument enum |
| 6 | `test_record_trade_raises_on_invalid_direction` | D-15: direction enum |
| 7 | `test_record_trade_raises_on_zero_or_negative_contracts` | D-15: n_contracts int>0 (zero, negative, and float=1.5 all raise) |
| 8 | `test_record_trade_raises_on_non_string_entry_date` | D-19: int 20260102 instead of str |
| 9 | `test_record_trade_raises_on_empty_string_exit_reason` | D-19: empty string |
| 10 | `test_record_trade_raises_on_bool_for_numeric_field` | D-19: `gross_pnl=True` rejected (isinstance quirk) |
| 11 | `test_record_trade_raises_on_nan_gross_pnl` | D-19: `float('nan')` raises at boundary |
| 12 | `test_record_trade_raises_on_inf_cost_aud` | D-19: `float('inf')` raises |
| 13 | `test_record_trade_raises_on_string_entry_price` | D-19: `'7000.0'` str rejected |
| 14 | `test_record_trade_does_not_mutate_caller_trade_dict` | **D-20:** caller's trade dict unchanged; trade_log entry is separate dict |
| 15 | `test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl` | **CRITICAL:** CORRECT path account=100_994.0; BUG path account=100_988.0; delta = closing_cost_half = 6.0 |

### `TestEquityHistory` (6 tests)

| # | Test | Proves |
|---|------|--------|
| 1 | `test_update_equity_history_appends_entry` | STATE-06: entry shape `{date, equity}` correct |
| 2 | `test_update_equity_history_appends_multiple_entries_in_order` | Chronological order preserved across 3 appends |
| 3 | `test_update_equity_history_returns_mutated_state` | `result is state` — same reference for chaining |
| 4 | `test_update_equity_history_raises_on_non_string_date` | B-4: int date raises ValueError |
| 5 | `test_update_equity_history_raises_on_short_date_string` | B-4: `'2026-04'` len=7 raises |
| 6 | `test_update_equity_history_raises_on_non_finite_equity` | B-4: NaN, inf, and True (bool) all raise |

## Functions Still Stubbed

**None.** All 6 public + 5 private functions of state_manager.py are fully implemented. PHASE GATE passed.

## Requirements Covered (this Wave)

- **STATE-05 complete** — record_trade atomic position close + trade_log append + account adjustment + D-15/D-19 validation + D-20 non-mutating contract.
- **STATE-06 complete** — update_equity_history caller-computed equity append + B-4 boundary validation.

## Requirements Covered (Phase 3 cumulative)

All 7 STATE-XX requirements have ≥1 named passing test:

| Req | Summary | Key tests |
|-----|---------|-----------|
| STATE-01 | 8 top-level keys; fresh state shape | `test_reset_state_has_all_8_top_level_keys`, `test_load_state_missing_file_returns_fresh_shape`, `test_load_state_valid_json_missing_keys_raises_value_error` (D-18) |
| STATE-02 | Atomic write durability | `test_crash_on_os_replace_leaves_original_intact`, `test_save_state_creates_readable_file`, `test_atomic_write_fsyncs_parent_dir_after_os_replace` (D-17) |
| STATE-03 | Corruption recovery | `test_corrupt_file_triggers_backup_and_reset`, `test_backup_uses_path_derived_name_not_hardcoded` (B-1) |
| STATE-04 | Schema migration | `test_schema_v1_no_op_migration`, `test_load_state_without_schema_version_key_migrates_to_current` |
| STATE-05 | record_trade | `test_record_trade_appends_to_trade_log_with_net_pnl`, `test_record_trade_adjusts_account_by_net_pnl`, 6 D-19 extended-validation tests, D-20 no-mutation test, CRITICAL Phase 4 boundary test |
| STATE-06 | update_equity_history | `test_update_equity_history_appends_entry`, 3 B-4 validation tests |
| STATE-07 | reset_state | `test_reset_state_canonical_default_values` |

## D-19 Extended Validation — Implementation Receipts

Two validation loops in `_validate_trade`:

1. **String-field loop (3 fields):**
   ```python
   for field in ('entry_date', 'exit_date', 'exit_reason'):
     value = trade[field]
     if not isinstance(value, str) or len(value) == 0:
       raise ValueError(f'record_trade: field {field!r} must be non-empty str, got {value!r}')
   ```
2. **Numeric-field loop (5 fields):**
   ```python
   for field in ('entry_price', 'exit_price', 'gross_pnl', 'multiplier', 'cost_aud'):
     value = trade[field]
     if (
       not isinstance(value, int | float)
       or isinstance(value, bool)
       or not math.isfinite(value)
     ):
       raise ValueError(f'record_trade: field {field!r} must be finite numeric '
                        f'(int or float, not bool, not NaN/inf), got {value!r}')
   ```

The bool-exclusion is critical: Python's `isinstance(True, int)` returns `True`, so without the explicit `isinstance(value, bool)` short-circuit, `gross_pnl=True` would silently compute `net_pnl = True - 6.0 = -5`. Test `test_record_trade_raises_on_bool_for_numeric_field` proves the guard fires.

## D-20 No-Mutation Contract — Receipt

`record_trade` body:
```python
# D-20: append a copy of trade WITH net_pnl, do NOT mutate caller's dict.
state['trade_log'].append(dict(trade, net_pnl=net_pnl))
```

The old mutating pattern `trade['net_pnl'] = net_pnl; state['trade_log'].append(trade)` is **NOT PRESENT** in state_manager.py (grep AC `trade['net_pnl'] = net_pnl` returns 0). Test `test_record_trade_does_not_mutate_caller_trade_dict` asserts:
- `'net_pnl' not in trade` after the call
- `set(trade.keys()) == original_keys`
- `result['trade_log'][0] is not trade` (different dict object)
- `result['trade_log'][0]['net_pnl'] == 994.0` (the copy HAS net_pnl)

## B-4 Equity-Boundary Validation — Receipt

`update_equity_history` body:
```python
# B-4: validate date shape
if not isinstance(date, str) or len(date) != 10:
  raise ValueError(f'update_equity_history: date must be str of length 10 (ISO YYYY-MM-DD), got {date!r}')
# B-4: validate equity is finite numeric (rejecting bool, NaN, ±inf)
if (
  not isinstance(equity, int | float)
  or isinstance(equity, bool)
  or not math.isfinite(equity)
):
  raise ValueError(f'update_equity_history: equity must be finite numeric '
                   f'(int or float, not bool, not NaN/inf), got {equity!r}')
```

Three tests prove the guard: non-string date (int 20260421), short date (`'2026-04'` len=7), and non-finite equity (NaN, inf, True).

## CRITICAL Phase 4 Boundary — Named Test

**Test:** `tests/test_state_manager.py::TestRecordTrade::test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl`

**Worked numerical example (SPI LONG, 2 contracts, $5/pt multiplier, $6 AUD round-trip cost):**

| Path | gross_pnl passed | net_pnl computed | account after | Comment |
|------|------------------|------------------|---------------|---------|
| CORRECT | 1000.0 (raw `(7100-7000)*2*5`) | 994.0 | 100_994.0 | What Phase 4 MUST do |
| BUG | 994.0 (`ClosedTrade.realised_pnl`) | 988.0 | 100_988.0 | Double-counting closing cost |

The delta assertion `(result['account'] - bug_result['account']) == closing_cost_half` proves the bug magnitude exactly equals the $6 closing-half cost — a clear diagnostic for any Phase 4 PR that misuses the boundary.

## Commits

| Task | Hash    | Commit Message |
|-----:|---------|----------------|
| 1    | b488d6a | feat(03-04): implement _validate_trade (D-15+D-19), record_trade (D-13/D-14/D-20), update_equity_history (D-04+B-4) |
| 2    | 4417cc2 | test(03-04): populate TestRecordTrade (15) + TestEquityHistory (6) — 21 tests incl. D-19 + D-20 + Phase 4 boundary + B-4 |

## Test Count Delta

| Metric | Before | After | Delta |
|--------|-------:|------:|------:|
| Full suite pass count | 273 | 294 | +21 |
| `tests/test_state_manager.py` passing | 24 | 45 | +21 |
| `state_manager.py` NotImplementedError stubs | 3 | **0** | -3 |
| `tests/test_state_manager.py` populated classes | 6 | **8** (all) | +2 |
| `tests/test_state_manager.py` `pass`-stub classes | 2 | 0 | -2 |

## Verification Gate Results

| Gate | Result |
|------|--------|
| `pytest tests/test_state_manager.py::TestRecordTrade -x -q` | **15/15 PASS** |
| `pytest tests/test_state_manager.py::TestEquityHistory -x -q` | **6/6 PASS** |
| `pytest tests/test_state_manager.py::TestRecordTrade::test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl -x -v` | PASS (CRITICAL AC) |
| `pytest tests/test_state_manager.py::TestRecordTrade::test_record_trade_does_not_mutate_caller_trade_dict -x -v` | PASS (D-20) |
| `pytest tests/test_state_manager.py::TestRecordTrade -k raises -x -v` | 10/10 PASS (validation paths) |
| `pytest tests/test_state_manager.py::TestEquityHistory -k raises -x -v` | 3/3 PASS (B-4) |
| `pytest tests/test_state_manager.py -x -q` | **45/45 PASS** |
| `pytest tests/ -q` | **294/294 PASS** (Phase 1 + Phase 2 + Phase 3 complete) |
| `pytest tests/test_signal_engine.py::TestDeterminism::test_state_manager_no_forbidden_imports -x -q` | PASS (hexagonal-lite intact) |
| `pytest tests/test_signal_engine.py::TestDeterminism::test_no_four_space_indent -x -q` | PASS (2-space indent preserved) |
| `ruff check state_manager.py tests/test_state_manager.py` | All checks passed |
| `grep -c 'NotImplementedError' state_manager.py` | **0** (PHASE GATE) |
| `grep -E '^(from|import) (signal_engine|sizing_engine|...)' state_manager.py` | empty (D-04 hex boundary enforced) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Ruff UP038 on both `isinstance(value, (int, float))` call sites**

- **Found during:** Task 1 ruff gate after initial implementation.
- **Issue:** Ruff rule UP038 (modernize isinstance to PEP 604 union syntax) flagged `isinstance(value, (int, float))` in `_validate_trade` (line 234) and `isinstance(equity, (int, float))` in `update_equity_history` (line 472). Ruff exits 1 with 2 errors.
- **Fix:** Converted both to `isinstance(value, int | float)` and `isinstance(equity, int | float)`. PEP 604 union syntax is semantically identical (both reject bool identically: `isinstance(True, int | float)` returns `True`, so the subsequent `isinstance(value, bool)` short-circuit fires in both forms). Plan AC greps use the new syntax's function-body intent; no AC grep specifically required the tuple form.
- **Files modified:** `state_manager.py` (2 sites in `_validate_trade` and `update_equity_history`).
- **Verification:** `ruff check state_manager.py` → `All checks passed!`; TestRecordTrade + TestEquityHistory all 21 tests pass (bool rejection and NaN/inf rejection both work correctly in the new form).
- **Committed in:** `b488d6a` (Task 1 — part of same implementation commit).

### Non-deviations (documented for clarity)

**2. D-20 no-mutation test uses double-quoted strings**

- The plan's test body has `assert 'net_pnl' not in trade, 'D-20: ... caller\\'s trade dict ...'` — escaped apostrophe inside single-quoted string.
- Python parses `\\'` as `\'` which would render as a literal backslash+apostrophe in the runtime assertion message (confusing when pytest prints the failure).
- Used double-quoted string literals for assertion messages that contain apostrophes. Functional behavior identical (still a str); assertion messages render cleanly (`caller's` not `caller\'s`).
- No AC grep was broken by this: the plan's AC `grep -F "'net_pnl' not in trade"` still matches 1 (the `assert` expression uses single quotes as in the plan).

**3. Task 1 `<verify>` runs against empty TestRecordTrade/TestEquityHistory**

- The plan's Task 1 verify step specifies `pytest tests/test_state_manager.py::TestRecordTrade tests/test_state_manager.py::TestEquityHistory`, but these classes are still `pass` skeletons at Task 1 commit time (Task 2 populates them). Pytest collects 0 tests there and returns exit 5.
- This is **by design in the plan**: the acceptance-criteria wording says "tests from Task 2" — Task 1 implements the functions, Task 2 adds the tests, both under `tdd="true"` but with the tests landing as a second commit for atomic history.
- Real verification is the full-suite run after Task 2: 294/294 PASS.
- No functional deviation.

## Threat Register Mitigations Delivered

| Threat ID | Category | Mitigation shipped |
|-----------|----------|---------------------|
| T-03-16 | Tampering | `_validate_trade` raises ValueError naming missing field(s); `test_record_trade_raises_on_missing_field` verifies |
| T-03-17 | Tampering | Instrument and direction enum checks per D-15; 2 tests verify |
| T-03-18 | Tampering | `n_contracts` int>0 with explicit bool rejection per D-15 + D-19 bool posture; `test_record_trade_raises_on_zero_or_negative_contracts` covers 0, -1, 1.5 |
| T-03-18b | Tampering | D-19 extended validation across all 8 remaining fields; 6 representative tests verify (non-string entry_date, empty exit_reason, bool gross_pnl, NaN gross_pnl, inf cost_aud, string entry_price) |
| T-03-19 | Tampering | record_trade docstring states "MUST NOT be Phase 2's ClosedTrade.realised_pnl"; `test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl` exercises CORRECT and BUG paths with worked arithmetic (account=100_994.0 vs 100_988.0; delta = closing_cost_half) |
| T-03-19b | Tampering | D-20 non-mutating append: `dict(trade, net_pnl=net_pnl)`; old `trade['net_pnl'] = net_pnl` pattern NOT present in source; `test_record_trade_does_not_mutate_caller_trade_dict` asserts `'net_pnl' not in trade` after the call |
| T-03-20 | Tampering | B-4 `math.isfinite(equity)` at update_equity_history boundary; test covers NaN, inf, and bool |
| T-03-20b | Tampering | B-4 date-shape validation (str of len 10); 2 tests verify (non-string + short string) |

All 8 Wave 3 threat-register mitigations shipped with test coverage.

## Phase 3 Phase-Gate State

**PASSING — ready for `/gsd-verify-work 3`**

- All 6 public + 5 private state_manager.py functions implemented (zero NotImplementedError stubs).
- All 7 STATE-XX requirements have ≥1 named passing test.
- Hexagonal-lite enforced: state_manager.py imports only stdlib + system_params; no signal_engine, sizing_engine, notifier, dashboard, main, or network-IO imports.
- 2-space indent enforced across touched files.
- Ruff clean on state_manager.py and tests/test_state_manager.py.
- Full test suite green: Phase 1 + Phase 2 + Phase 3 → 294 passing tests.

## Open Items for Phase 4 Wire-up

1. **Read `state_manager.record_trade` docstring + `test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl` BEFORE projecting ClosedTrade → trade dict.** The boundary is the #1 most dangerous Phase 3→4 hand-off contract.
2. **Compute gross_pnl explicitly:**
   - LONG: `gross_pnl = (exit_price - entry_price) * n_contracts * multiplier`
   - SHORT: `gross_pnl = (entry_price - exit_price) * n_contracts * multiplier`
   - **NEVER** pass `ClosedTrade.realised_pnl` as `gross_pnl` — that double-counts the closing-half cost by $6/trade for SPI, $2.50/trade for AUDUSD.
3. **Phase 4 can safely reuse the trade dict after calling record_trade** — D-20 guarantees it is NOT mutated (the `net_pnl` lives on the trade_log entry copy, not the input).
4. **For `update_equity_history`:** format `date` as ISO YYYY-MM-DD (length 10 exactly) and ensure `equity` is finite (`math.isfinite`) before calling, or be ready to handle ValueError from B-4 validation.
5. **First-run file materialization:** after `load_state()` on a fresh machine, explicitly call `save_state(state)` — B-3 guarantees load_state does NOT auto-save on missing file (orchestrator owns materialization).
6. **Warning emission is orchestrator's responsibility:** state_manager is the sole writer to `state['warnings']` via `append_warning`. Any subsystem that needs to emit a warning must call `append_warning(state, source, message)` (optionally with `now=` for tests) rather than directly appending.

## Final Test Count

- **Phase 1:** ~99 tests (signal_engine + indicators)
- **Phase 2:** ~150 tests (sizing_engine + pyramiding + exits)
- **Phase 3:** 45 tests (state_manager — 12 Wave 1 + 12 Wave 2 + 21 Wave 3)
- **Full suite:** 294 tests

## Self-Check: PASSED

**File existence:**
- `state_manager.py` (modified): FOUND at `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.claude/worktrees/agent-a4bd8d98/state_manager.py`
- `tests/test_state_manager.py` (modified): FOUND at `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.claude/worktrees/agent-a4bd8d98/tests/test_state_manager.py`
- `.planning/phases/03-state-persistence-with-recovery/03-04-SUMMARY.md` (this file): FOUND at `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.claude/worktrees/agent-a4bd8d98/.planning/phases/03-state-persistence-with-recovery/03-04-SUMMARY.md`

**Commit existence (in worktree branch history):**
- `b488d6a` feat(03-04): FOUND
- `4417cc2` test(03-04): FOUND

**Verification gates (all green):**
- Full test suite: 294/294 PASS
- Phase 3 targeted: 45/45 PASS
- CRITICAL Phase 4 boundary test: PASS
- D-20 no-mutation test: PASS
- D-19 validation tests (10 matching `-k raises` in TestRecordTrade): 10/10 PASS
- B-4 validation tests (3 matching `-k raises` in TestEquityHistory): 3/3 PASS
- AST guard (state_manager.py forbidden-imports): PASS
- 2-space indent guard: PASS
- Ruff: clean on both touched files
- Zero NotImplementedError stubs in state_manager.py (PHASE GATE)

---

*Phase: 03-state-persistence-with-recovery*
*Plan: 04 (Wave 3 — PHASE GATE)*
*Completed: 2026-04-21*
