---
phase: 27
plan: 07
type: execute
wave: 1
parallel: true
depends_on: []
files_modified:
  - state_manager.py
  - tests/test_naive_datetime_fail_closed.py
  - tests/test_migration_contiguity.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Any datetime.now() / datetime.fromisoformat() in state-write paths that yields naive datetime raises ValueError('naive datetime forbidden — must be tz-aware')."
    - "Read paths from old state files keep a guarded UTC-coercion shim with deprecation warning."
    - "load_state asserts every consecutive integer 1 → STATE_SCHEMA_VERSION has a registered _migrate_vN_to_vN+1 entry; missing migrator raises clear message at module-load time."
  artifacts:
    - path: state_manager.py
      provides: "_assert_tz_aware helper + _assert_migration_chain_contiguous + ValueError fail-closed write paths"
      contains: "_assert_migration_chain_contiguous"
    - path: tests/test_naive_datetime_fail_closed.py
      provides: "regression for ValueError on naive datetime write"
      contains: "naive datetime forbidden"
    - path: tests/test_migration_contiguity.py
      provides: "regression for missing-migrator fail-fast"
      contains: "_MIGRATIONS"
  key_links:
    - from: "state_manager.save_state"
      to: "_assert_tz_aware"
      via: "validation before write"
      pattern: "_assert_tz_aware"
    - from: "state_manager (module-load)"
      to: "_assert_migration_chain_contiguous"
      via: "called at import time"
      pattern: "_assert_migration_chain_contiguous\\(\\)"
---

<objective>
Two related state_manager.py hardening items bundled (both touch state_manager, both are guard-clauses):

1. **Naive-datetime fail-closed (item #6):** any datetime arithmetic in write paths must reject naive datetimes with `ValueError('naive datetime forbidden — must be tz-aware')`. Read paths from legacy state files keep a guarded UTC-coercion shim with `warnings.warn(...)`.
2. **Schema-migration contiguity assert (item #12):** at module-load time, walk `_MIGRATIONS` dict and assert every integer pair from 1 → STATE_SCHEMA_VERSION has a registered key. No gaps.

Bundled because they share the same file (state_manager.py) and the same defensive-coding category (fail-fast on invalid state).

Purpose: time-confusion prevention (#6) + silent state-corruption prevention (#12).
Output: 2 helpers + 4+ regression tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@state_manager.py

<interfaces>
# state_manager.py current naive-risk sites:
#   line 661 — `now = datetime.now(UTC)`  ✓ already tz-aware
#   line 799 — `now = datetime.now(UTC)`  ✓ already tz-aware
# But:
#   line 25 (docstring) mentions "datetime.now(timezone.utc)" — pattern is documented as the rule
# Other files with naive risk (read-only audit, not write paths — out of this plan's scope unless they reach state writes):
#   notifier.py:1631 — datetime.fromisoformat(expires_at) — magic-link verification path, NOT state-write
#   notifier.py:1970 — datetime.now(pytz.timezone('Australia/Perth')) — tz-aware ✓
#   auth_store.py — many datetime.now(timezone.utc).isoformat() — tz-aware ✓
#
# So state_manager itself is already clean. The fail-closed addition is:
#   _assert_tz_aware(dt: datetime, *, context: str) -> None:
#     if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
#       raise ValueError(f'naive datetime forbidden — must be tz-aware (context: {context})')
# Call at the head of any save_state-adjacent helper that takes a datetime arg.
#
# Migration chain — current _MIGRATIONS dict (state_manager.py lines 303-309):
#   _MIGRATIONS = { 2: _migrate_v1_to_v2, 3: _migrate_v2_to_v3, ..., 8: _migrate_v7_to_v8 }
# Plan 27-01 ADDS key 9. Contiguity assertion:
#   def _assert_migration_chain_contiguous():
#     assert STATE_SCHEMA_VERSION >= 1
#     missing = [v for v in range(2, STATE_SCHEMA_VERSION + 1) if v not in _MIGRATIONS]
#     if missing:
#       raise RuntimeError(
#         f'_MIGRATIONS chain has gaps: missing keys {missing} '
#         f'(STATE_SCHEMA_VERSION={STATE_SCHEMA_VERSION})'
#       )
# Call at module bottom: `_assert_migration_chain_contiguous()` — fails at import.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: _assert_tz_aware fail-closed on write paths</name>
  <read_first>
    - state_manager.py lines 25-30 (existing tz-aware doc)
    - state_manager.py lines 580-700 (save_state body — every datetime write)
    - state_manager.py lines 660-680 (now = datetime.now(UTC) — already correct)
  </read_first>
  <behavior>
    - test_assert_tz_aware_rejects_naive: _assert_tz_aware(datetime(2026,1,1), context='test') raises ValueError with message containing 'naive datetime forbidden'.
    - test_assert_tz_aware_accepts_aware: _assert_tz_aware(datetime(2026,1,1,tzinfo=timezone.utc), context='test') does not raise.
    - test_save_state_with_naive_datetime_in_payload_raises: build a state dict with a naive datetime nested somewhere persisted — save_state raises ValueError clearly. (If state.json doesn't directly persist datetime objects but ISO strings, the gate is in the function that BUILDS the ISO string from a datetime; the helper guards there.)
    - test_load_state_with_naive_iso_in_legacy_file_warns: build a fake legacy state.json with a naive ISO timestamp (e.g. '2026-01-01T00:00:00' with no offset); load_state succeeds but emits DeprecationWarning('naive ISO datetime coerced to UTC — please re-save'). Use pytest.warns.
  </behavior>
  <action>
1. **state_manager.py:** add `_assert_tz_aware` helper near the top of the helper block (after imports, before _migrate_*):
   ```python
   def _assert_tz_aware(dt: datetime, *, context: str) -> None:
     '''Phase 27 #6 — fail-closed on naive datetimes in write paths.'''
     if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
       raise ValueError(f'naive datetime forbidden — must be tz-aware (context: {context})')
   ```
2. Audit save_state path for any function taking a datetime arg. Currently, save_state takes a state dict (not a datetime directly), and the datetime-ish fields are ISO strings already. Add the gate at any point a `datetime` typed value is converted to an ISO string for persistence — find via grep `\.isoformat()` in state_manager.py.
3. **Read-path UTC-coercion shim:** in the load_state body, around the json.load result, walk known datetime-string fields. If `datetime.fromisoformat(s).tzinfo is None`, emit `warnings.warn('naive ISO datetime coerced to UTC — please re-save', DeprecationWarning, stacklevel=2)` and coerce via `.replace(tzinfo=timezone.utc)`. Track which fields these are by inspecting save_state output.
4. **tests/test_naive_datetime_fail_closed.py (NEW):** 4 tests per behavior block.
  </action>
  <verify>
    <automated>pytest tests/test_naive_datetime_fail_closed.py -x -v</automated>
  </verify>
  <done>
    - _assert_tz_aware in state_manager.py.
    - Load-path UTC-coercion shim in place with DeprecationWarning.
    - 4 tests in test_naive_datetime_fail_closed.py green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: _assert_migration_chain_contiguous fail-fast at import</name>
  <read_first>
    - state_manager.py lines 300-320 (_MIGRATIONS dict)
    - state_manager.py lines 425-440 (load_state migration walk)
  </read_first>
  <behavior>
    - test_migration_chain_contiguous_passes_at_import: `import importlib; importlib.reload(state_manager)` succeeds (no exception) — proves the in-tree chain has no gaps.
    - test_migration_chain_with_gap_raises: in a test, monkey-construct a fake _MIGRATIONS dict missing key=5 (with STATE_SCHEMA_VERSION=8), call _assert_migration_chain_contiguous() directly, assert RuntimeError with message containing 'missing keys [5]'.
    - test_migration_chain_called_on_module_load: read the source — assert the LAST line of state_manager.py (or near it) is `_assert_migration_chain_contiguous()` (string match).
  </behavior>
  <action>
1. **state_manager.py:** add `_assert_migration_chain_contiguous` helper per <interfaces> AFTER the `_MIGRATIONS = { ... }` block.
2. Call it at module-bottom (after `_MIGRATIONS` is defined and before any test fixture imports the module).
3. **Important:** Plan 27-01 will ALSO bump STATE_SCHEMA_VERSION to 9 and add `_migrate_v8_to_v9`. The contiguity check must pass with that 27-01 change in place. If 27-01 lands first (it's same wave), the chain is 1→9 with all keys 2-9 present. If 27-07 lands first, the chain is 1→8 with keys 2-8 — also passes. Both orderings are fine because each plan keeps the chain contiguous.
4. **tests/test_migration_contiguity.py (NEW):** 3 tests per behavior block. Test 2 (gap-detection) MUST construct a fake migrations dict in the test body (not patching the real module dict, which would break other tests — use a local dict + call the helper with a stubbed STATE_SCHEMA_VERSION via monkeypatch).
   ```python
   def test_migration_chain_with_gap_raises(monkeypatch):
     fake_migrations = {2: lambda s: s, 3: lambda s: s, 4: lambda s: s, 6: lambda s: s, 7: lambda s: s, 8: lambda s: s}  # missing 5
     monkeypatch.setattr(state_manager, '_MIGRATIONS', fake_migrations)
     monkeypatch.setattr(state_manager, 'STATE_SCHEMA_VERSION', 8)
     with pytest.raises(RuntimeError, match=r'missing keys \[5\]'):
       state_manager._assert_migration_chain_contiguous()
   ```
  </action>
  <verify>
    <automated>pytest tests/test_migration_contiguity.py -x -v</automated>
  </verify>
  <done>
    - _assert_migration_chain_contiguous in state_manager.py.
    - Called at module-bottom (verifiable by import succeeding).
    - 3 tests in test_migration_contiguity.py green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| state.json (disk) → in-memory state | Schema version mismatch must fail clearly, not silently corrupt |
| Wall-clock datetime → state-persistence | Naive datetime confuses cross-tz comparisons |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-07-01 | Tampering (self) | Future contributor adds _migrate_v9_to_v10 but skips registering in _MIGRATIONS dict — silently breaks new-deployment migrations | mitigate | _assert_migration_chain_contiguous fails at module load — hard error visible at first `python -c 'import state_manager'`. |
| T-27-07-02 | Tampering | Naive datetime persisted, later compared with tz-aware → silent ordering bug | mitigate | _assert_tz_aware gate; legacy data warned and coerced. |
| T-27-07-03 | DoS | Module-load check on every import has tiny cost | accept | <1ms; runs once per process. |
</threat_model>

<verification>
```
pytest tests/test_naive_datetime_fail_closed.py tests/test_migration_contiguity.py -x -v
python -c 'import state_manager'  # must succeed (chain green for current STATE_SCHEMA_VERSION)
pytest -x   # full suite
```
</verification>

<success_criteria>
- _assert_tz_aware + _assert_migration_chain_contiguous helpers in state_manager.py.
- Migration-chain check called at module-load.
- 7 tests across 2 new test files green.
- Full suite green.
</success_criteria>

<output>
Create `27-07-SUMMARY.md` with: helper signatures, call sites, current chain state (1→9 if 27-01 landed first, else 1→8), test count.
</output>
