---
phase: 27
plan: 07
type: execute
wave: 1A
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
    - "Any datetime arg passed to a state-write helper that is naive raises ValueError('naive datetime forbidden — must be tz-aware')."
    - "Read paths from old state files keep a guarded UTC-coercion shim with deprecation warning."
    - "load_state asserts every consecutive integer 1 → STATE_SCHEMA_VERSION has a registered _migrate_vN_to_vN+1 entry; missing migrator raises clear message AT the point load_state would fail (behavior, not source-position)."
  artifacts:
    - path: state_manager.py
      provides: "_assert_tz_aware helper + _assert_migration_chain_contiguous + ValueError fail-closed write paths"
      contains: "_assert_migration_chain_contiguous"
    - path: tests/test_naive_datetime_fail_closed.py
      provides: "regression for ValueError on naive datetime write"
      contains: "naive datetime forbidden"
    - path: tests/test_migration_contiguity.py
      provides: "behavioral regression: missing-migrator fail at load (not source-position)"
      contains: "_MIGRATIONS"
  key_links:
    - from: "state_manager.save_state"
      to: "_assert_tz_aware"
      via: "validation before write"
      pattern: "_assert_tz_aware"
    - from: "state_manager.load_state"
      to: "_assert_migration_chain_contiguous"
      via: "called at load before migration walk"
      pattern: "_assert_migration_chain_contiguous"
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `1` → `1A`; depends_on remains empty (this plan blocks 27-01 which is Wave 1B).
- [x] M1 (brittle implementation tests — source-position check) — replaced "last line of module is `_assert_migration_chain_contiguous()`" check with behavioral test: `load_state` called against a state with non-contiguous chain raises BEFORE returning. Tests behavior, not source-position. The contiguity check still RUNS at module-load time (defensive); tests just don't assert on source positioning.
- [x] M2 (doc rule) — SUMMARY artifact stays inside `.planning/phases/27-.../`.
- [x] Codex MEDIUM (state may store ISO strings not datetime objects) — clarified: the `_assert_tz_aware` gate fires at the function that BUILDS the ISO string from a datetime arg (e.g. helpers like `_isoformat_aware(dt)`), not at the bytes-on-disk layer. Read path UTC-coercion shim handles legacy naive ISO.

<objective>
Two related state_manager.py hardening items bundled (both touch state_manager, both are guard-clauses):

1. **Naive-datetime fail-closed (item #6):** any datetime arg into a state-write helper must reject naive datetimes with `ValueError('naive datetime forbidden — must be tz-aware')`. Read paths from legacy state files keep a guarded UTC-coercion shim with `warnings.warn(...)`.
2. **Schema-migration contiguity assert (item #12):** at module-load time AND at load_state entry, walk `_MIGRATIONS` dict and assert every integer pair from 1 → STATE_SCHEMA_VERSION has a registered key. No gaps.

Bundled because they share the same file (state_manager.py) and the same defensive-coding category.

Purpose: time-confusion prevention (#6) + silent state-corruption prevention (#12).
Output: 2 helpers + 7+ regression tests (behavior-level, not source-position-level).
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
# Other production files audit — read-only:
#   notifier.py:1631 — datetime.fromisoformat(expires_at) — magic-link path, NOT state-write
#   auth_store.py — many datetime.now(timezone.utc) — tz-aware ✓
#
# The fail-closed addition:
#   def _assert_tz_aware(dt: datetime, *, context: str) -> None:
#     if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
#       raise ValueError(f'naive datetime forbidden — must be tz-aware (context: {context})')
# Call at the head of any helper that takes a datetime arg and produces an ISO string for state.
# Identify call sites: grep `\.isoformat()` in state_manager.py — wherever a datetime arg flows
# to .isoformat(), insert the gate at the helper boundary.
#
# Migration chain — current _MIGRATIONS dict (lines 303-309):
#   _MIGRATIONS = { 2: _migrate_v1_to_v2, ..., 8: _migrate_v7_to_v8 }
# Plan 27-01 ADDS key 9. Contiguity assertion:
#   def _assert_migration_chain_contiguous():
#     assert STATE_SCHEMA_VERSION >= 1
#     missing = [v for v in range(2, STATE_SCHEMA_VERSION + 1) if v not in _MIGRATIONS]
#     if missing:
#       raise RuntimeError(
#         f'_MIGRATIONS chain has gaps: missing keys {missing} '
#         f'(STATE_SCHEMA_VERSION={STATE_SCHEMA_VERSION})'
#       )
# CALL POSITIONS (review-fix M1 — behavioral check, not source-position assertion):
#   1. At module bottom (after _MIGRATIONS dict is defined) — defensive, fails at import.
#   2. At load_state() entry — fails BEFORE returning state, even if module-load check was somehow bypassed.
# Tests verify the BEHAVIOR (load_state fails on non-contiguous chain) — not the source-line position.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: _assert_tz_aware fail-closed on write paths</name>
  <read_first>
    - state_manager.py lines 25-30 (existing tz-aware doc)
    - state_manager.py lines 580-700 (save_state body — every datetime write)
    - state_manager.py — grep `\.isoformat()` to find datetime-to-string call sites
  </read_first>
  <behavior>
    - test_assert_tz_aware_rejects_naive: _assert_tz_aware(datetime(2026,1,1), context='test') raises ValueError with 'naive datetime forbidden'.
    - test_assert_tz_aware_accepts_aware: _assert_tz_aware(datetime(2026,1,1,tzinfo=timezone.utc), context='test') does not raise.
    - test_save_state_with_naive_datetime_in_payload_raises: build a state dict with a naive datetime nested; save_state raises ValueError clearly.
    - test_load_state_with_naive_iso_in_legacy_file_warns: build a fake legacy state.json with a naive ISO timestamp ('2026-01-01T00:00:00' no offset); load_state succeeds but emits DeprecationWarning. Use pytest.warns.
  </behavior>
  <action>
1. **state_manager.py:** add `_assert_tz_aware` helper near top of helper block (after imports, before _migrate_*):
   ```python
   def _assert_tz_aware(dt: datetime, *, context: str) -> None:
     '''Phase 27 #6 — fail-closed on naive datetimes in write paths.'''
     if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
       raise ValueError(f'naive datetime forbidden — must be tz-aware (context: {context})')
   ```

2. Audit save_state path: grep `\.isoformat()` in state_manager.py. For every helper that takes a datetime and converts to ISO, insert `_assert_tz_aware(dt, context='helper_name')` at function entry.

3. **Read-path UTC-coercion shim:** in the load_state body, around the json.load result, walk known datetime-string fields. If `datetime.fromisoformat(s).tzinfo is None`:
   ```python
   warnings.warn('naive ISO datetime coerced to UTC — please re-save', DeprecationWarning, stacklevel=2)
   coerced = naive.replace(tzinfo=timezone.utc)
   ```

4. **tests/test_naive_datetime_fail_closed.py (NEW):** 4 tests per behavior block.
  </action>
  <verify>
    <automated>pytest tests/test_naive_datetime_fail_closed.py -x -v</automated>
  </verify>
  <done>
    - _assert_tz_aware in state_manager.py.
    - Load-path UTC-coercion shim with DeprecationWarning.
    - 4 tests green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: _assert_migration_chain_contiguous — fail-fast at module load AND at load_state (behavioral)</name>
  <!-- review-fix: M1 — behavioral test, not source-position assertion -->
  <read_first>
    - state_manager.py lines 300-320 (_MIGRATIONS dict)
    - state_manager.py lines 425-440 (load_state migration walk)
  </read_first>
  <behavior>
    - test_migration_chain_contiguous_passes_at_import: `import importlib; importlib.reload(state_manager)` succeeds — proves the in-tree chain has no gaps.
    - test_migration_chain_with_gap_raises_at_helper_call: monkey-construct a fake _MIGRATIONS dict missing key=5 (with STATE_SCHEMA_VERSION=8); call _assert_migration_chain_contiguous() directly; assert RuntimeError with 'missing keys [5]'.
    - test_load_state_fails_on_non_contiguous_chain: monkey-patch _MIGRATIONS to have a gap; call load_state on a valid state file; assert RuntimeError raises BEFORE state is returned. THIS IS THE BEHAVIORAL TEST replacing the brittle source-position check.  <!-- review-fix: M1 -->
    - test_migration_chain_called_at_load_state_entry: trace via mock — when load_state runs, _assert_migration_chain_contiguous is called early (before json.load result is migrated). Verify via side-effect (assertion raises before json read).
  </behavior>
  <action>
1. **state_manager.py:** add `_assert_migration_chain_contiguous` helper per <interfaces> AFTER the `_MIGRATIONS = { ... }` block.

2. **Two call sites (review-fix M1 — defensive AND behavioral):**
   - At module bottom (after _MIGRATIONS): `_assert_migration_chain_contiguous()` — fails at import.
   - At load_state() entry (before json.load result is processed): `_assert_migration_chain_contiguous()` — fails on each load even if module-load somehow skipped.

3. **Important:** Plan 27-01 lands AFTER this plan (Wave 1B vs 1A) and bumps STATE_SCHEMA_VERSION to 9 with `_migrate_v8_to_v9`. The contiguity check must pass with each landing:
   - After 27-07 lands: chain is 1→8 with keys 2-8 — contiguous, passes.
   - After 27-01 lands: chain is 1→9 with keys 2-9 — contiguous, passes.

4. **tests/test_migration_contiguity.py (NEW):** 4 tests per behavior block. Test 2 (gap-detection):
   ```python
   def test_migration_chain_with_gap_raises_at_helper_call(monkeypatch):
     fake_migrations = {2: lambda s: s, 3: lambda s: s, 4: lambda s: s,
                        6: lambda s: s, 7: lambda s: s, 8: lambda s: s}  # missing 5
     monkeypatch.setattr(state_manager, '_MIGRATIONS', fake_migrations)
     monkeypatch.setattr(state_manager, 'STATE_SCHEMA_VERSION', 8)
     with pytest.raises(RuntimeError, match=r'missing keys \[5\]'):
       state_manager._assert_migration_chain_contiguous()
   ```
   Test 3 (behavioral — load_state behavior):
   ```python
   def test_load_state_fails_on_non_contiguous_chain(monkeypatch, tmp_path):
     # Place a valid state.json
     fake_state_path = tmp_path / 'state.json'
     fake_state_path.write_text(json.dumps({'schema_version': 1, 'account_aud': 1000}))
     monkeypatch.setattr(state_manager, 'STATE_PATH', fake_state_path)
     # Inject a gap
     fake_migrations = {2: lambda s: s, 4: lambda s: s}  # missing 3
     monkeypatch.setattr(state_manager, '_MIGRATIONS', fake_migrations)
     monkeypatch.setattr(state_manager, 'STATE_SCHEMA_VERSION', 4)
     with pytest.raises(RuntimeError, match=r'missing keys \[3\]'):
       state_manager.load_state()
   ```
   Behavioral, not source-position-based.
  </action>
  <verify>
    <automated>pytest tests/test_migration_contiguity.py -x -v</automated>
  </verify>
  <done>
    - _assert_migration_chain_contiguous in state_manager.py.
    - Called at module bottom AND at load_state entry.
    - 4 tests green (incl. behavioral load_state-fails test).
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
| T-27-07-01 | Tampering (self) | Future contributor adds _migrate_v9_to_v10 but skips registering in _MIGRATIONS dict | mitigate | _assert_migration_chain_contiguous fails at module load AND at load_state entry. |
| T-27-07-02 | Tampering | Naive datetime persisted, later compared with tz-aware → silent ordering bug | mitigate | _assert_tz_aware gate; legacy data warned and coerced. |
| T-27-07-03 | DoS | Module-load + load_state checks have tiny cost | accept | <1ms; runs once per process + per load_state call. |
</threat_model>

<verification>
```
pytest tests/test_naive_datetime_fail_closed.py tests/test_migration_contiguity.py -x -v
python -c 'import state_manager'  # must succeed
pytest -x   # full suite
```
</verification>

<success_criteria>
- _assert_tz_aware + _assert_migration_chain_contiguous helpers in state_manager.py.
- Migration-chain check called at module-load AND at load_state entry.
- 8 tests across 2 new test files green (behavioral, not source-position).
- Full suite green.
</success_criteria>

<output>
Create `27-07-SUMMARY.md` with: helper signatures, call sites, current chain state, test count + behavioral-test rationale.
</output>
