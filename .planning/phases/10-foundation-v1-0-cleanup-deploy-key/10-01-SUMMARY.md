---
phase: 10
plan: 01
subsystem: state-manager + orchestrator (BUG-01 defense-in-depth)
tags: [bug-fix, regression-test, defense-in-depth, cli, state-manager, tdd]
requires:
  - Phase 3 state_manager.reset_state factory (baseline)
  - Phase 8 _handle_reset CLI + interactive Q&A paths (existing)
provides:
  - state_manager.reset_state(initial_account: float = INITIAL_ACCOUNT) -> dict
  - main.py::_handle_reset one-line state['account'] sync
  - invariant state['account'] == state['initial_account'] enforced at two layers
affects:
  - tests/test_state_manager.py (new TestResetState class)
  - tests/test_main.py (new TestHandleReset class)
tech-stack:
  added: []
  patterns: [defense-in-depth, module-boundary-invariant, TDD RED/GREEN]
key-files:
  created: []
  modified:
    - state_manager.py (signature extension, ~6 lines changed)
    - main.py (1 new line in _handle_reset)
    - tests/test_state_manager.py (new TestResetState class — 4 tests)
    - tests/test_main.py (new TestHandleReset class — 3 tests)
decisions:
  - Rule 3 deviation on Task 2 Test 3 test_reset_default_initial_account_still_syncs — plan's draft snippet set _stdin_isatty=False AND omitted --initial-account, but current _handle_reset rejects that combo with exit 2 (non-TTY guard). Test adjusted to provide --initial-account=str(INITIAL_ACCOUNT) so the path actually reaches the D-01 fix. Invariant still exercised.
metrics:
  duration: 6m48s
  completed: 2026-04-24T11:01:27Z
  tasks: 2
  commits: 4
  files: 4
---

# Phase 10 Plan 01: BUG-01 Defense-in-Depth — state['account'] / state['initial_account'] invariant

## One-liner
Closed BUG-01 at two layers — `reset_state()` signature extension (D-02) + `_handle_reset` one-line call-site fix (D-01) — so `state['account']` and `state['initial_account']` can no longer drift after a `--reset`.

## Summary

v1.0 carry-over: the dashboard total-return formula produced spurious +900% readings on day one because `reset_state()` left `account=INITIAL_ACCOUNT` while `_handle_reset` wrote `initial_account=CLI-arg`. Plan 10-01 fixed this at both layers:

1. **Module boundary (D-02)**: `state_manager.reset_state()` now accepts an optional `initial_account: float = INITIAL_ACCOUNT` kwarg. Both `state['account']` and `state['initial_account']` are derived from the same `float(initial_account)` source, so they can never diverge at the factory layer. Default value preserves backward compat for Phase 3 callers + the corrupt-recovery path inside `load_state`.

2. **Call site (D-01)**: `main.py::_handle_reset` now writes `state['account'] = float(initial_account)` immediately after the existing `state['initial_account'] = float(initial_account)` line. Even if a future caller reaches in and mutates `initial_account` without going through the factory, the call-site fix still enforces the pairing.

Both fixes together produce defense-in-depth: any BUG-01 regression would require BOTH the factory AND the call-site override to break simultaneously.

## Files Changed

| File | Change | Lines |
|------|--------|-------|
| `state_manager.py` | Extended `reset_state` signature with `initial_account` kwarg; docstring updated with Phase 10 D-02 traceability; both `account` and `initial_account` dict entries now wrap with `float(initial_account)` | +12 / -4 |
| `main.py` | One new line in `_handle_reset`: `state['account'] = float(initial_account)  # Phase 10 BUG-01 D-01: sync account to initial_account` | +1 |
| `tests/test_state_manager.py` | New `TestResetState` class with 4 tests (custom `initial_account`, edge $1, default backward-compat, other-fields-unchanged) | +42 |
| `tests/test_main.py` | New `TestHandleReset` class with 3 tests (CLI-flag path, interactive Q&A path, default-INITIAL_ACCOUNT path) | +75 |

## Tests Added

| Class | Count | Tests |
|-------|-------|-------|
| `tests/test_state_manager.py::TestResetState` | 4 | `test_reset_state_accepts_custom_initial_account`, `test_reset_state_custom_initial_account_edge_one_dollar`, `test_reset_state_default_preserves_backward_compat`, `test_reset_state_custom_initial_account_does_not_affect_other_fields` |
| `tests/test_main.py::TestHandleReset` | 3 | `test_reset_syncs_account_to_initial_account_cli_flag_path`, `test_reset_syncs_account_to_initial_account_interactive_path`, `test_reset_default_initial_account_still_syncs` |

**Total new tests: 7** (plan target: 7 — plan mentions "4+3" and success criteria says "7 new regression tests")

## Test Suite Delta

| | Baseline | After Plan 10-01 |
|-|----------|------------------|
| Total passing | 662 | 669 |
| Delta | — | +7 |

Zero regression on existing `TestReset`, `TestResetFlags`, `TestResetInteractive`, or any other suite.

## Ruff Status

Zero new warnings introduced by this plan.

- `main.py`: unchanged ruff status (0 errors either way).
- `state_manager.py`: pre-existing `I001` on the import block (line 34) is unchanged by my edit — deferred to a later plan (out of scope per scope-boundary rule).
- `tests/test_state_manager.py`: pre-existing 2 errors at lines 16/219 — unchanged by my additions.
- `tests/test_main.py`: pre-existing 11 errors at lines 1840+ (past my insertion) — unchanged.

Confirmed via `git stash`/`stash pop` ruff comparison before and after.

## Commit SHAs

| # | Task | Phase | Hash | Message |
|---|------|-------|------|---------|
| 1 | Task 1 | RED | `1f4391a` | `test(10-01): add TestResetState for D-02 reset_state signature extension` |
| 2 | Task 1 | GREEN | `3ea6665` | `feat(10-01): extend reset_state signature with initial_account kwarg (D-02)` |
| 3 | Task 2 | RED | `6dbd0f4` | `test(10-01): add TestHandleReset for D-01 CLI + interactive regression` |
| 4 | Task 2 | GREEN | `4a4aa91` | `fix(10-01): _handle_reset syncs state['account'] to initial_account (D-01)` |

All commits used `--no-verify` per parallel-executor worktree discipline to avoid pre-commit hook contention with other parallel agents in this wave.

## TDD Gate Compliance

RED and GREEN commits exist for BOTH tasks in strict order:
- Task 1: `test(...)` commit `1f4391a` preceded `feat(...)` commit `3ea6665` — gate sequence valid.
- Task 2: `test(...)` commit `6dbd0f4` preceded `fix(...)` commit `4a4aa91` — gate sequence valid.

REFACTOR gate not needed — both implementations were minimal (signature extension + one-line fix), no cleanup warranted.

RED phase was validated before GREEN in both tasks: 3 of 4 TestResetState tests failed with `TypeError: reset_state() got an unexpected keyword argument 'initial_account'`; 2 of 3 TestHandleReset tests failed with `AssertionError: assert 100000.0 == 50000.0` on `state['account']` comparison — the exact BUG-01 manifestation.

## Deviations from Plan

### Rule 3 deviation — Task 2 Test 3 `test_reset_default_initial_account_still_syncs`

**Found during:** Task 2 RED phase design.

**Issue:** The plan's draft snippet for this test set `monkeypatch.setattr('main._stdin_isatty', lambda: False)` AND omitted `--initial-account` from the argv:

```python
monkeypatch.setattr('main._stdin_isatty', lambda: False)  # non-TTY = no prompting
...
rc = main.main([
  '--reset',
  '--spi-contract', 'spi-mini',
  '--audusd-contract', 'audusd-standard',
])
```

The current `_handle_reset` (main.py:1163) rejects "non-TTY + missing flags" with exit 2:
```python
if not has_explicit_flags and not _stdin_isatty():
  print('[State] ERROR: Non-interactive shell detected...')
  return 2
```

So the plan snippet would have exited 2 at the guard, never reaching the D-01 fix, and the test would have failed with `assert rc == 0` before exercising the invariant.

**Fix:** Kept the non-TTY setup (to prove default-path works in non-interactive environment), but added an explicit `--initial-account str(int(INITIAL_ACCOUNT))` flag so the CLI-flag path is taken and the D-01 fix is exercised. Invariant still asserted:
```python
assert s['account'] == s['initial_account']
assert s['account'] == float(INITIAL_ACCOUNT)
```

**Why Rule 3:** This is a blocking issue for completing the current task — the plan snippet as written could not produce a passing GREEN-phase test. The adjustment preserves the intent ("default-INITIAL_ACCOUNT path still holds invariant") while working within the existing non-TTY guard contract.

**No user approval needed:** Rule 3 auto-fix — the test still covers the default-path invariant, just via a CLI-explicit rather than prompt-omit form.

### No other deviations
No Rule 1 (bug) or Rule 2 (missing functionality) deviations. No auth gates. No checkpoints hit. All 7 tests green on first GREEN run after each feat/fix commit.

## Acceptance Criteria Status

All 19 plan-specified acceptance criteria green:

**Task 1 (D-02):**
- [x] `grep -q "def reset_state(initial_account" state_manager.py`
- [x] `grep -q "Phase 10 BUG-01 D-02" state_manager.py`
- [x] `grep -q "'account': float(initial_account)" state_manager.py`
- [x] `grep -q "'initial_account': float(initial_account)" state_manager.py`
- [x] `grep -q "class TestResetState" tests/test_state_manager.py`
- [x] `grep -c "def test_reset_state" tests/test_state_manager.py` = 7 (>=4)
- [x] `pytest tests/test_state_manager.py::TestResetState -q` 4/4 green
- [x] `pytest tests/test_state_manager.py::TestReset -q` 3/3 green (zero regression)
- [x] `ruff check state_manager.py tests/test_state_manager.py` — zero NEW warnings

**Task 2 (D-01):**
- [x] `grep -q "state\['account'\] = float(initial_account)" main.py`
- [x] `grep -q "Phase 10 BUG-01 D-01" main.py`
- [x] `grep -q "class TestHandleReset" tests/test_main.py`
- [x] `grep -q "test_reset_syncs_account_to_initial_account_cli_flag_path" tests/test_main.py`
- [x] `grep -q "test_reset_syncs_account_to_initial_account_interactive_path" tests/test_main.py`
- [x] `pytest tests/test_main.py::TestHandleReset -q` 3/3 green
- [x] `pytest tests/test_main.py::TestResetFlags tests/test_main.py::TestResetInteractive -q` 17/17 green (zero regression)
- [x] `ruff check main.py tests/test_main.py` — zero NEW warnings
- [x] D-01 line count sanity: `grep -c "state\['account'\] = float(initial_account)" main.py` = 1

**Plan overall:**
- [x] `pytest -q` — 669/669 green (baseline 662 + 7 new)

## Threat Flags

None. Plan 10-01 touches no secrets, no network, no file system paths beyond the existing state.json write inside `_handle_reset`. No new attack surface introduced.

## Known Stubs

None. Both fixes are real, not placeholders.

## Self-Check: PASSED

Verified post-write:
- `state_manager.py` — `grep -q "def reset_state(initial_account"` FOUND
- `main.py` — `grep -q "Phase 10 BUG-01 D-01"` FOUND
- `tests/test_state_manager.py` — `grep -q "class TestResetState"` FOUND
- `tests/test_main.py` — `grep -q "class TestHandleReset"` FOUND
- Commits `1f4391a`, `3ea6665`, `6dbd0f4`, `4a4aa91` all present in `git log --oneline -5`
