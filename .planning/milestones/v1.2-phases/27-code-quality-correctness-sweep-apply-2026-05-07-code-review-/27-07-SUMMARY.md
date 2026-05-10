---
phase: 27
plan: 07
subsystem: state_manager
tags: [defensive-coding, datetime, schema-migration, fail-closed]
dependency_graph:
  requires: []
  provides:
    - "_assert_tz_aware helper (state-write fail-closed)"
    - "_assert_migration_chain_contiguous helper (load-time + import-time)"
    - "_coerce_legacy_naive_iso shim (read-path UTC coercion)"
  affects:
    - "Plan 27-01 (Wave 1B) bumps STATE_SCHEMA_VERSION to 9 — contiguity check will validate the new key registration"
tech_stack:
  added:
    - "stdlib `warnings` module (DeprecationWarning emission on read path)"
  patterns:
    - "fail-closed gate at write-helper boundary (raise BEFORE mutation)"
    - "observe-and-warn shim on read path (legacy compat without nuking files)"
    - "module-load defensive guard + per-call defensive guard (M1 review-fix)"
key_files:
  created:
    - tests/test_naive_datetime_fail_closed.py
    - tests/test_migration_contiguity.py
  modified:
    - state_manager.py
decisions:
  - "Read-path shim emits ONE DeprecationWarning per load (early-break) rather than per-row to avoid spamming on a 365-day equity_history."
  - "_coerce_legacy_naive_iso scans equity_history only — `warnings.date` and `last_run` are date-only YYYY-MM-DD strings (no T separator), out of scope."
  - "Contiguity check runs at module bottom (defensive, fails at import) AND at load_state entry (review-fix M1: behavioral, fails on every load)."
  - "Tests assert observable BEHAVIOR (load_state raises pre-migration; no migrator invoked) — not source-line position. Replaces the brittle 'last line of module is …' check from the original draft."
metrics:
  duration: 8m24s
  completed: 2026-05-07
---

# Phase 27 Plan 07: Naive-datetime fail-closed + migration-chain contiguity — Summary

State-manager defensive hardening: caller-supplied naive datetimes now raise `ValueError('naive datetime forbidden — must be tz-aware')` at the write-helper boundary, legacy state files keep loading via a UTC-coercion shim that emits `DeprecationWarning`, and any future contributor who bumps `STATE_SCHEMA_VERSION` without registering the new migrator hits a `RuntimeError` at module-load AND at every `load_state()` entry.

## What changed

### `state_manager.py`

| Helper | Purpose | Call sites |
|---|---|---|
| `_assert_tz_aware(dt, *, context)` | raises `ValueError('naive datetime forbidden — must be tz-aware (context: …)')` if `dt.tzinfo is None` or `dt.tzinfo.utcoffset(dt) is None` | `append_warning` head (after `now=` defaulting) |
| `_coerce_legacy_naive_iso(state)` | walks `equity_history` rows; if a `date` field is a datetime-shaped string with no offset, emits `DeprecationWarning('naive ISO datetime in legacy state coerced to UTC — please re-save')` once and returns the unchanged dict | `load_state` happy path, after `_validate_loaded_state` |
| `_assert_migration_chain_contiguous()` | walks `range(2, STATE_SCHEMA_VERSION + 1)`; raises `RuntimeError('MIGRATIONS chain has gaps: missing keys [N, …] (STATE_SCHEMA_VERSION=K)')` on any gap | (1) module bottom, after `MIGRATIONS = { … }` block; (2) `load_state()` entry, before the `path.exists()` short-circuit |

### Current chain state (post-27-07, pre-27-01)

```
STATE_SCHEMA_VERSION = 8
MIGRATIONS keys      = {1, 2, 3, 4, 5, 6, 7, 8}   ← contiguous (1 is no-op anchor)
```

When Plan 27-01 (Wave 1B) lands, it will bump STATE_SCHEMA_VERSION to 9 and add key 9 to the dict — the contiguity check will validate the registration is contiguous on first import after the bump.

### Tests

| File | Tests | Style |
|---|---|---|
| `tests/test_naive_datetime_fail_closed.py` | 5 | helper contract (2) + write-path fail-closed pair (2) + read-path coercion (1) |
| `tests/test_migration_contiguity.py` | 4 | behavioral (NOT source-position) — module-reload, helper-with-gap, load_state-with-gap, no-migrator-invoked |

**Behavioral-test rationale (review-fix M1):** the original plan draft had a test asserting "the last source-line of `state_manager.py` is `_assert_migration_chain_contiguous()`". That test would break on any source rearrangement (e.g., adding a docstring at the bottom, moving the call). The replacement asserts the OBSERVABLE outcome — `load_state` on a gapped chain raises `RuntimeError` BEFORE returning, and no migrator was invoked — which is brittle-resistant and exercises the actual production code path the operator depends on.

## Verification

```
$ .venv/bin/python -m pytest tests/test_naive_datetime_fail_closed.py tests/test_migration_contiguity.py -v
9 passed in 0.03s

$ .venv/bin/python -c 'import state_manager; print("ok")'
ok

$ .venv/bin/python -m pytest
1803 passed in 112.00s
```

## Commits

| Hash | Type | Description |
|---|---|---|
| `1927992` | test | RED — naive datetime fail-closed regression tests |
| `46f7235` | feat | GREEN — `_assert_tz_aware` + `_coerce_legacy_naive_iso` |
| `1a04da0` | test | RED — migration contiguity behavioral regressions |
| `d2bd771` | feat | GREEN — `_assert_migration_chain_contiguous` (module + load_state) |

## TDD Gate Compliance

Both tasks followed RED → GREEN cycle. Each task has a `test(...)` commit immediately followed by a `feat(...)` commit. No REFACTOR commit was needed (helpers shipped clean on first GREEN). Plan-level gate: PASSED.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Test-fixture bug] Legacy-state contract labels**
- **Found during:** Task 1 GREEN run
- **Issue:** Initial test fixture used `'mini'` / `'standard'` as contract labels; `load_state` materialises `_resolved_contracts` via `SPI_CONTRACTS[label]` and raised `KeyError: 'mini'` because the canonical labels in `system_params.py` are `spi-mini` / `audusd-standard`.
- **Fix:** Imported `state_manager._DEFAULT_SPI_LABEL` / `_DEFAULT_AUDUSD_LABEL` and used those — single source of truth for canonical label names.
- **Files modified:** `tests/test_naive_datetime_fail_closed.py`
- **Commit:** folded into `46f7235` (GREEN Task 1) so the RED → GREEN diff stayed coherent

No other deviations.

## Threat Surface Scan

No new network endpoints, auth paths, file-access patterns, or trust-boundary schema changes introduced. Both helpers are pure in-memory guards — no new threat flags.

## Self-Check: PASSED

- [x] `state_manager.py` exists and contains `_assert_tz_aware`, `_assert_migration_chain_contiguous`, `_coerce_legacy_naive_iso`
- [x] `tests/test_naive_datetime_fail_closed.py` exists (5 tests)
- [x] `tests/test_migration_contiguity.py` exists (4 tests)
- [x] Commits `1927992`, `46f7235`, `1a04da0`, `d2bd771` all reachable from HEAD
- [x] Full suite green: 1803/1803
