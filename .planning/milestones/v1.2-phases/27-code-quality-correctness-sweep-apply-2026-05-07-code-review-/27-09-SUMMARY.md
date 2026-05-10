---
phase: 27
plan: 09
subsystem: state-shape unification — bare-int signal back-compat removal
tags:
  - phase-27
  - signal-shape
  - schema-migration
  - back-compat-removal
  - v9-to-v10
  - phase-26-debt-r5
dependency_graph:
  requires:
    - 27-01-decimal-money-math-PLAN.md  # schema bump must follow Decimal migration (chain v8→v9 first)
    - 27-07-naive-datetime-and-migration-contiguity-PLAN.md  # _assert_migration_chain_contiguous must exist
  provides:
    - "_migrate_v9_to_v10 promoting bare-int signal rows to dict shape"
    - "STATE_SCHEMA_VERSION = 10 (bumped from 9)"
    - "dict-only invariant: state['signals'][market_id] is always dict"
    - "reset_state() writes dict-shape signals (no bare-int sources remain)"
  affects:
    - "Renderer dashboard_renderer/components/signals.py defensive int branch deleted"
    - "Future signal-row consumers can drop their own isinstance(sig_entry, int) defensives"
    - "main.py:1187/1389 + dashboard.py:1148 + sizing_engine.py:150 still carry defensive int branches but they are now dead code at runtime (legacy state.json files migrate at load_state) — removal deferred to a follow-up sweep"
tech_stack:
  added: []
  patterns:
    - "Schema-bump migrator: v9→v10 promotes bare-int to {signal: int, strategy_version: STRATEGY_VERSION} on load"
    - "Source-side fix: reset_state() writes dict shape so no NEW bare-int rows can ever enter the system"
    - "Defensive deletion: renderer's isinstance(sig_entry, int) elif removed once invariant holds"
    - "Plan-vs-reality reconciliation: production uses field name `signal` (NOT `direction` as plan text said) — Rule 1 deviation tracked in commit + tests"
key_files:
  created:
    - tests/test_signal_shape_migration.py
  modified:
    - system_params.py
    - state_manager.py
    - dashboard_renderer/components/signals.py
    - tests/test_state_manager.py
    - tests/test_system_params.py
    - tests/test_decimal_money_math.py
    - tests/test_naive_datetime_fail_closed.py
    - tests/fixtures/dashboard/empty_state.json
    - tests/fixtures/dashboard/golden_empty.html
decisions:
  - "Production field name is `signal`, NOT `direction` — plan's <interfaces> block was stale. Migrator + tests + reset_state all use `signal` key to match main.py:1190, dashboard_renderer/components/signals.py:45, sizing_engine.py:153."
  - "reset_state() updated to write dict-shape signals. Truth #1 mandates dict-only, including fresh state. Without this, every fresh post-reset state would re-introduce bare-int rows that the v10 migrator would silently re-promote on next load — wasted work and a confusing source of truth split."
  - "Plan Task 2's mechanical refactor doesn't apply uniformly: ~17 test sites in test_state_manager.py seed bare-int as INPUT to OLD migrators (`_migrate_v3_to_v4` etc.). These represent legacy on-disk state and MUST stay bare-int — they're testing the migration path, not the current shape. Only test sites that seed `schema_version: STATE_SCHEMA_VERSION` were converted (4 sites + 1 in test_naive_datetime_fail_closed.py)."
  - "tests/test_main.py:644 + 718 explicitly test the legacy bare-int upgrade-on-write path — the comment `'Phase 3 int shape'` is load-bearing. Left untouched. Runtime defensive branches in main.py:1187/1389 still consume them; deferred to future cleanup once we're sure no in-the-wild state.json files carry bare-int."
  - "Plan grep gate `signals\\['KEY'\\] = N` form does not appear in this codebase — all bare-ints are dict-literal-style (`'signals': {'SPI200': 0, ...}`). Both formal plan gates pass at zero matches."
metrics:
  duration: ~30min
  tasks: 2
  files_modified: 8
  files_created: 1
  tests_added: 9
  tests_passing: 1926/1926 (full suite, +9 net new from 1917 baseline post-27-10)
  completed: 2026-05-08
---

# Phase 27 Plan 27-09: Bare-Int Signal Shape Unification — Summary

Phase 26 DEBT.md R5 closed: the bare-int signal back-compat path is gone. `state['signals'][market_id]` is now dict-shaped only. The renderer's defensive `isinstance(sig_entry, int)` branch (`dashboard_renderer/components/signals.py:35-39` pre-cleanup) is deleted. A new v9→v10 schema migrator promotes any legacy bare-int rows on load. `reset_state()` writes dict shape directly so no fresh-state path re-introduces bare-int.

## What shipped

### `system_params.py` — schema bump

`STATE_SCHEMA_VERSION: 9 → 10`. The trailing comment now records the Phase 27 #11 (Plan 27-09) lineage alongside prior schema bumps.

### `state_manager.py` — migrator + reset cleanup

```python
def _migrate_v9_to_v10(s: dict) -> dict:
  '''Promote any bare-int signal rows to dict shape.

  Pre-migration legacy shape (Phase 3 reset_state):
    state['signals']['SPI200'] = 0   # FLAT
    state['signals']['SPI200'] = 1   # LONG
    state['signals']['SPI200'] = -1  # SHORT

  Post-migration canonical shape:
    state['signals']['SPI200'] = {
      'signal': 0 | 1 | -1,
      'strategy_version': STRATEGY_VERSION,
    }
  '''
  signals = s.get('signals', {})
  if not isinstance(signals, dict):
    return s
  out_signals = dict(signals)
  for k, v in signals.items():
    if isinstance(v, int) and not isinstance(v, bool):
      out_signals[k] = {'signal': v, 'strategy_version': STRATEGY_VERSION}
  out = dict(s)
  out['signals'] = out_signals
  return out

MIGRATIONS[10] = _migrate_v9_to_v10
```

Properties:

- **Idempotent.** Already-dict rows pass through unchanged. No `strategy_version` overwrite, no `last_close` / `last_scalars` / `ohlc_window` mutation.
- **Defensive.** Bool excluded (`True is 1` in Python's ABC tree). Non-dict `signals` value returns unchanged.
- **Silent.** No `append_warning`, no log line — D-15 silent-migration convention (mirrors v3→v4 / v4→v5 / v6→v7 / v7→v8 / v8→v9).
- **Field name.** Uses production field name `signal` (NOT `direction` as the plan text said — plan deviation Rule 1).

`reset_state()` now writes:

```python
'signals': {
  'SPI200': {'signal': 0, 'strategy_version': STRATEGY_VERSION},
  'AUDUSD': {'signal': 0, 'strategy_version': STRATEGY_VERSION},
}
```

This is a **source-side fix** that matters: without it, every reset would silently re-introduce bare-int rows that the v10 migrator would re-promote on next load — wasted cycles and a split source of truth. Plan deviation Rule 2 (correctness — required for truth #1 invariant to hold).

### `dashboard_renderer/components/signals.py` — defensive branch removed

```python
# Before:
elif isinstance(sig_entry, int):
  signal_int = sig_entry
  label = html.escape(d._SIGNAL_LABEL.get(sig_entry, d._fmt_em_dash()), quote=True)
  signal_as_of_line = 'Signal as of never'
  scalars_line = html.escape(d._fmt_em_dash(), quote=True)
else:
  signal_int = sig_entry.get('signal', 0)
  ...

# After:
else:
  # Phase 27 #11 (Plan 27-09): bare-int branch deleted. After v9->v10
  # migration runs at load_state, sig_entry is guaranteed to be a dict
  # (or None — handled above). Phase 26 DEBT.md R5.
  signal_int = sig_entry.get('signal', 0)
  ...
```

Truth #2 satisfied. AST grep over module body (after stripping comments + docstrings via line-walker) returns zero `isinstance(.*int.*)` matches.

### Tests

#### `tests/test_signal_shape_migration.py` — NEW (9 tests, all green)

| Class | Test | Asserts |
|---|---|---|
| TestMigrateV9ToV10 | test_promotes_bare_int_to_dict | `_migrate_v9_to_v10({signals: {SPI200: 0, AUDUSD: 1}})` returns dict-shaped, `signal` key set, `strategy_version == STRATEGY_VERSION` |
| TestMigrateV9ToV10 | test_idempotent_on_already_dict | dict-shape row passes through unchanged; `strategy_version='v1.0.0'` NOT overwritten; running twice yields same output |
| TestMigrateV9ToV10 | test_negative_int_shape_short_signal_promoted | `-1` (SHORT) bare-int promoted to `{signal: -1, strategy_version: ...}` |
| TestRendererDefensiveIntBranchRemoved | test_no_isinstance_int_branch | regex over signals.py source (with comments/docstrings stripped) finds zero `isinstance(..., int)` |
| TestRendererRendersDictSignal | test_renders_dict_signal_long | dict signal=1 → `status-dot--long` class in HTML |
| TestRendererRendersDictSignal | test_renders_dict_signal_flat_zero | dict signal=0 → `status-dot--flat` class |
| TestChainContiguityHoldsAfterV10Bump | test_state_schema_version_is_10 | `STATE_SCHEMA_VERSION == 10` |
| TestChainContiguityHoldsAfterV10Bump | test_migrations_registered_for_every_int_in_chain | all keys [2..10] registered in MIGRATIONS; key 10 is `_migrate_v9_to_v10` |
| TestChainContiguityHoldsAfterV10Bump | test_assert_migration_chain_contiguous_passes | `_assert_migration_chain_contiguous()` does not raise |

#### Cascade-fixed tests (Rule 1 — schema-version assertions cascaded v9→v10)

- `tests/test_system_params.py::test_state_schema_version_is_8` — value asserted v10 with explanatory comment (test name kept for git-history continuity, mirroring the same pattern Plan 27-01 used when bumping v8→v9).
- `tests/test_decimal_money_math.py::test_v8_to_v9_migration_coerces_money` — assertion loosened to `STATE_SCHEMA_VERSION >= 9` so it covers both Plan 27-01 (v9 at write time) and Plan 27-09 (v10 here).
- `tests/test_state_manager.py` — 4 chain-end assertions (v9→v10) at lines 2563, 2628, 2727, 2783.
- `tests/test_state_manager.py` — 3 reset_state shape assertions (lines 168, 906, 957) updated to dict-shape `state['signals']['SPI200']['signal'] == 0` form.
- `tests/test_state_manager.py::TestMigrateV2Backfill::test_v1_state_gets_only_phase8_keys_backfilled` — `_migrate(state)` walks v1→v10, so the bare-int signals input is now promoted to dict shape by the chain. Assertion updated accordingly.

#### Fixtures regenerated

- `tests/fixtures/dashboard/empty_state.json` — schema_version 8 → 10; `signals` updated to dict shape with `strategy_version: 'v1.2.0'`.
- `tests/fixtures/dashboard/golden_empty.html` — regenerated. The `<div class="strategy-version">` footer now renders `v1.2.0` (was `v1.0.0` default for bare-int rows). This is the **correct** new behavior since reset_state now stamps `strategy_version` on every signal row.

#### Current-state seeds refactored to dict shape

| File | Line | Schema |
|---|---|---|
| tests/test_state_manager.py | 113 | STATE_SCHEMA_VERSION |
| tests/test_state_manager.py | 512 | STATE_SCHEMA_VERSION |
| tests/test_state_manager.py | 1070 | STATE_SCHEMA_VERSION |
| tests/test_state_manager.py | 1346 | STATE_SCHEMA_VERSION |
| tests/test_naive_datetime_fail_closed.py | 89 | STATE_SCHEMA_VERSION |

These are seeds at the CURRENT schema version. Migration-input seeds (schema_version 1/3/4/7 or absent) were intentionally NOT touched — they represent legacy on-disk state and ARE the migration test fixtures.

## TDD Gate Compliance

Task 1 followed RED → GREEN. Task 2 was a follow-up refactor task with no new behavior, committed as `test(...)` (test-only fixture/seed updates).

| Hash | Type | Description |
|---|---|---|
| `b01118a` | test | RED — 9 failing tests for v10 migrator + renderer cleanup + chain contiguity |
| `ec19652` | feat | GREEN Task 1 — v10 migrator + signals.py cleanup + reset_state dict shape + cascade-fix |
| `1483ec5` | test | Task 2 — refactor current-state seeds to dict shape; legacy-input seeds untouched |

Plan-level gate: PASSED. RED commit precedes GREEN commits; sequence verifiable in `git log`.

## Verification

```
$ .venv/bin/python -m pytest tests/test_signal_shape_migration.py -x -v
  → 9 passed in 0.07s

$ grep -n 'isinstance.*int' dashboard_renderer/components/signals.py
  → (zero matches)

$ grep -rE "signals\[['\"][A-Z0-9_]+['\"]\]\s*=\s*-?[0-9]\s*$" tests/
  → (zero matches)

$ .venv/bin/python -m pytest
  → 1926 passed in 117.75s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Plan vs reality] Field name: `signal`, not `direction`.**

- **Found during:** Task 1 read_first reading of `dashboard_renderer/components/signals.py`, `main.py`, and `sizing_engine.py`.
- **Issue:** Plan's `<interfaces>` block specifies the dict shape as `{'direction': -1|0|1, 'strategy_version': '…'}`. Production code uses `signal` as the field name (see main.py:1190, dashboard_renderer/components/signals.py:45, sizing_engine.py:153, dashboard.py:1154 — all five sites read `sig_entry.get('signal')` or `sig_entry['signal']`).
- **Fix:** Migrator + reset_state + tests all use `signal` key. Plan deviation noted in commit messages and the migrator docstring.

**2. [Rule 2 — Correctness] reset_state must write dict shape.**

- **Found during:** Task 1 — analysing what calls produce bare-int rows in the codebase.
- **Issue:** Plan listed renderer cleanup + 38-test refactor + migrator. It did NOT mandate fixing `reset_state()` itself. But `reset_state()` was the ONLY production code path producing bare-int rows. Without fixing it, every fresh state would re-introduce bare-int rows, the v10 migrator would re-promote them on next load, and the dict-only invariant (truth #1) would be violated in-memory between reset and first save→load cycle.
- **Fix:** `reset_state()` now writes `{'SPI200': {'signal': 0, 'strategy_version': STRATEGY_VERSION}, ...}`. Three test assertions in `tests/test_state_manager.py` (`test_load_state_missing_file_returns_fresh_shape`, `test_reset_state_canonical_default_values`, `test_reset_state_custom_initial_account_does_not_affect_other_fields`) updated to the new shape. The dashboard golden_empty.html was regenerated because `_resolve_strategy_version(state)` now finds the populated `strategy_version` field on dict-shape rows and surfaces `v1.2.0` in the footer (was `v1.0.0` default).

**3. [Rule 1 — Test cascade] Schema-version assertions cascaded v9→v10.**

- **Found during:** Task 1 GREEN suite run.
- **Issue:** Six test assertions hardcoded `STATE_SCHEMA_VERSION == 9` (or `'must end at 9'` / similar string forms) — pre-existed before this plan, broke when STATE_SCHEMA_VERSION bumped to 10. Same class of cascade Plan 27-01 paid when bumping v8→v9.
- **Fix:** Cascade-updated to v10 with comments referencing Phase 27 #11 (Plan 27-09). One assertion (`test_v8_to_v9_migration_coerces_money`) loosened from `== 9` to `>= 9` so it doesn't break on the next schema bump.

**4. [Rule 1 — Fixture regeneration] Dashboard golden out of sync with reset_state shape.**

- **Found during:** Task 1 GREEN suite run.
- **Issue:** `tests/fixtures/dashboard/empty_state.json` carried bare-int signals at `schema_version: 8`. The dashboard render-from-fixture test (`TestEmptyState`) renders from `state_manager.reset_state()` (now dict-shape with `strategy_version`), but the regenerator script reads the JSON fixture (still bare-int → no `strategy_version` field reachable → footer defaults to `v1.0.0`). Result: `_resolve_strategy_version` returned `v1.0.0` for the golden but `v1.2.0` for the live render — 17-byte diff at byte 48970.
- **Fix:** Updated `empty_state.json` to schema_version=10 dict-shape signals with `strategy_version: 'v1.2.0'`. Regenerated `golden_empty.html`. Both render paths (reset_state-driven and JSON-fixture-driven) now produce byte-identical output.

### Plan-spec adjustments

**1. Plan asked to "update all 38+ test sites" — actual count was ~28 dict-literal sites + 0 direct-assignment sites.**

The plan's grep gate looks for direct assignments (`signals['KEY'] = N`). That form does NOT exist in this codebase — every bare-int site is in a dict-literal seed `'signals': {'KEY': N}`. Both grep gates (`isinstance.*int` in signals.py and direct-assignment form in tests) pass at zero matches.

**2. ~17 test sites with legacy schema (`schema_version: 1/3/4/7`) intentionally NOT refactored.**

These are inputs to OLD migrators — `_migrate_v3_to_v4`, `_migrate_v6_to_v7`, full-walk tests starting at v1, etc. They represent legacy on-disk state and ARE the migration test fixtures. Replacing the bare-int input with dict shape would erase what they're testing. They will continue to be valid until/unless the legacy migrators themselves are removed (out of scope here).

**3. tests/test_main.py:644 + 718 — explicit upgrade-shape compat test left untouched.**

Comment `'Phase 3 int shape'` is load-bearing. Test verifies main.py's daily-loop "read int OR dict, always write dict" upgrade-on-write path (the runtime branches in main.py:1187/1389 are NOT in scope for this plan).

**4. Defensive `isinstance(sig_entry, int)` branches left in main.py:1187/1389, dashboard.py:1148, sizing_engine.py:150.**

Plan's must_haves only call out `dashboard_renderer/components/signals.py:35-39` for removal. The other defensive branches consume bare-int values that the v10 migrator would have already promoted by the time they execute (load_state runs the chain), so they're effectively dead code — but removing them broadens the blast radius beyond what this plan scoped. Deferred to a follow-up sweep once we're confident no production state.json files carry pre-v10 schema.

### Authentication gates

None — no auth surface touched.

## Threat surface scan

Plan threat register:

| Threat ID | Disposition | Status |
|---|---|---|
| T-27-09-01 (legacy state.json with bare-int signals + renderer cleanup landed → AttributeError on render) | mitigate | **MITIGATED** — `_migrate_v9_to_v10` runs at every `load_state` invocation (chain walker calls it whenever schema_version < 10). Tests cover migration (3 tests), idempotency (1 test), and chain contiguity (3 tests). |
| T-27-09-02 (Tampering) | accept | accepted, unchanged. |

No new network endpoints, auth paths, file-access patterns, or trust-boundary schema changes. No new threat flags.

## Self-Check: PASSED

- [x] `state_manager.py` contains `_migrate_v9_to_v10`; `MIGRATIONS[10]` registered
- [x] `system_params.STATE_SCHEMA_VERSION == 10`
- [x] `dashboard_renderer/components/signals.py` no longer contains `isinstance(sig_entry, int)` branch
- [x] `state_manager.reset_state()` writes dict-shape signals with `strategy_version`
- [x] `tests/test_signal_shape_migration.py` exists (9 tests, all green)
- [x] `tests/fixtures/dashboard/empty_state.json` updated to v10 dict shape
- [x] `tests/fixtures/dashboard/golden_empty.html` regenerated
- [x] All 3 commits (`b01118a`, `ec19652`, `1483ec5`) reachable from HEAD
- [x] Full suite green: 1926/1926 (+9 net new tests from 1917 baseline)
- [x] Migration chain contiguity check still green (`_assert_migration_chain_contiguous` in test 9)
- [x] Plan grep gates: `isinstance.*int` in signals.py = 0 matches; bare-int direct-assignment in tests/ = 0 matches
