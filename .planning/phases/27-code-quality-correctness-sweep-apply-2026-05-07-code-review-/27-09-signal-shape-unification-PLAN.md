---
phase: 27
plan: 09
type: execute
wave: 2
parallel: false
depends_on:
  - 27-01-decimal-money-math-PLAN.md
  - 27-07-naive-datetime-and-migration-contiguity-PLAN.md
files_modified:
  - state_manager.py
  - dashboard_renderer/components/signals.py
  - tests/test_state_manager.py
  - tests/test_main.py
  - tests/test_notifier.py
  - tests/test_dashboard.py
  - tests/test_signal_shape_migration.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "state['signals'][market_id] is dict-shaped only (with at minimum keys {direction, strategy_version})."
    - "Renderer's defensive `isinstance(record, int)` branch in dashboard_renderer/components/signals.py:35-39 is REMOVED."
    - "All 38+ test sites that seeded `state['signals']['SPI200'] = 0` migrated to dict shape `{'direction': 0, 'strategy_version': STRATEGY_VERSION}`."
    - "_migrate_v9_to_v10 (or v8→v9 if 27-01 didn't ship Decimal) promotes any bare-int signals row found at load time."
    - "STATE_SCHEMA_VERSION bumped (10 if Plan 27-01 landed, else 9)."
  artifacts:
    - path: state_manager.py
      provides: "_migrate_vN_to_vN+1 promoting bare-int signals to dict"
      contains: "def _migrate_v"
    - path: dashboard_renderer/components/signals.py
      provides: "defensive int branch removed"
      contains: "signals.py"
  key_links:
    - from: "_migrate_vN_to_vN+1"
      to: "_assert_migration_chain_contiguous"
      via: "newly registered key"
      pattern: "_MIGRATIONS\\["
---

<objective>
Drop bare-int signal back-compat per Phase 26 DEBT.md R5. State shape `state['signals'][market_id]` is always a dict. Migrate any legacy bare-int rows at load time. Delete the renderer's defensive `isinstance(record, int)` branch (signals.py:35-39). Update all 38+ test sites to use dict shape.

Sequenced AFTER 27-01 (schema version) and 27-07 (migration-chain contiguity assert) so the schema bump fits cleanly into the now-checked chain.

Purpose: shape unification (review item #11). Phase 26 DEBT.md R5 explicitly flags this.
Output: schema bump + migration + 38-site test refactor + renderer cleanup.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/26-phase-25-followup-multi-tab-scoping-fixes/26-DEBT.md
@state_manager.py
@dashboard_renderer/components/signals.py

<interfaces>
# Current dict shape (from Phase 22 D-04/D-05):
#   state['signals']['SPI200'] = {
#     'direction': -1 | 0 | 1,            # FLAT=0, LONG=1, SHORT=-1
#     'strategy_version': 'v1.2.0',       # from STRATEGY_VERSION at write time
#     'as_of': '2026-05-07',              # YYYY-MM-DD AWST
#     'ohlc_window': [...],               # Phase 17 trace data
#     'indicator_scalars': {...},         # Phase 17 trace data
#   }
#
# Bare-int sentinel (legacy + 38 test sites):
#   state['signals']['SPI200'] = 0  # FLAT
#   state['signals']['SPI200'] = 1  # LONG
#   state['signals']['SPI200'] = -1 # SHORT
#
# Renderer defensive branch (dashboard_renderer/components/signals.py:35-39):
#   ...
#   elif isinstance(sig_entry, int):
#     # legacy bare-int — render as plain direction with no version/trace
#     direction = sig_entry
#     version = 'unknown'
#   ...
# DELETE this elif. After migration, only dict shape reaches the renderer.
#
# Migration: take next available schema version (depends on whether 27-01 landed):
#   If STATE_SCHEMA_VERSION=9 (after 27-01) → bump to 10, register _migrate_v9_to_v10.
#   If STATE_SCHEMA_VERSION=8 (without 27-01) → bump to 9, register _migrate_v8_to_v9.
# Body: for k, v in s.get('signals', {}).items(): if isinstance(v, int):
#         s['signals'][k] = {'direction': v, 'strategy_version': STRATEGY_VERSION, 'as_of': None}
#
# 38 test sites — discover via:
#   grep -rn "signals\['[A-Z0-9_]\+'\] = [-0-9]" tests/
#   grep -rn 'signals\["[A-Z0-9_]\+"\] = [-0-9]' tests/
# Mechanical replacement per site:
#   from old:  state['signals']['SPI200'] = 0
#   to new:    state['signals']['SPI200'] = {'direction': 0, 'strategy_version': STRATEGY_VERSION, 'as_of': '2026-05-07'}
# Add a test fixture helper to centralise:
#   def _signal_dict(direction: int, version: str = STRATEGY_VERSION, as_of: str = '2026-05-07') -> dict:
#     return {'direction': direction, 'strategy_version': version, 'as_of': as_of}
# Place in tests/conftest.py.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: _migrate_vN_to_vN+1 + schema bump + renderer cleanup</name>
  <read_first>
    - state_manager.py lines 232-310 (existing migrators, _MIGRATIONS dict)
    - dashboard_renderer/components/signals.py (full)
    - tests/conftest.py (centralised fixtures)
  </read_first>
  <behavior>
    - test_migrate_promotes_bare_int_to_dict: _migrate_vN_to_vN+1({signals: {SPI200: 0, AUDUSD: 1}}, ...) returns {signals: {SPI200: {direction: 0, strategy_version: 'v1.2.0', as_of: None}, AUDUSD: {direction: 1, ...}}}.
    - test_migrate_idempotent_on_already_dict: row already dict-shaped passes through unchanged.
    - test_renderer_no_isinstance_int_branch: read dashboard_renderer/components/signals.py source; assert `isinstance(.*int)` does NOT appear (regex grep).
    - test_renderer_renders_dict_signal: pass a dict-shaped signal entry through the component's render function; assert correct HTML output.
    - test_chain_contiguity_holds_after_bump: import state_manager — _assert_migration_chain_contiguous must succeed (catches the case where the migrator was added but not registered).
  </behavior>
  <action>
1. **Determine new STATE_SCHEMA_VERSION:** read current value. Add 1. Register the new migrator.

2. **state_manager.py:** define `_migrate_vN_to_vN+1` per <interfaces>. Register in `_MIGRATIONS` dict.

3. **dashboard_renderer/components/signals.py:** delete the `elif isinstance(sig_entry, int):` block (lines 35-39 per Phase 26 DEBT.md). After deletion, the function expects dict shape and would `KeyError` / `AttributeError` on bare int — but the migrator at load time guarantees this never happens in production paths.

4. **Add _signal_dict helper in tests/conftest.py** per <interfaces>.

5. **tests/test_signal_shape_migration.py (NEW):** 5 tests per behavior block.
  </action>
  <verify>
    <automated>pytest tests/test_signal_shape_migration.py -x -v</automated>
  </verify>
  <done>
    - Migrator registered; chain contiguity check still green.
    - Renderer defensive branch deleted (grep confirms).
    - Helper _signal_dict in conftest.
    - 5 migration tests green.
  </done>
</task>

<task type="auto">
  <name>Task 2: Refactor 38 test sites — bare int → dict shape</name>
  <read_first>
    - tests/test_state_manager.py
    - tests/test_main.py
    - tests/test_notifier.py
    - tests/test_dashboard.py
    - (any other test file matching the grep below)
  </read_first>
  <action>
1. Discover all test sites:
   ```bash
   grep -rn 'signals\[.[A-Z0-9_]\+.\]\s*=\s*-\?[0-9]' tests/
   ```
   Capture the exact list (file:line:content). Expected ~38 matches per Phase 26 DEBT.md.

2. For each match, mechanical substitution:
   ```python
   # before
   state['signals']['SPI200'] = 0
   # after
   state['signals']['SPI200'] = _signal_dict(0)
   ```
   Import _signal_dict from conftest at top of each touched test file (or rely on pytest's fixture-import via conftest auto-discovery — `_signal_dict` as a module-level helper in conftest.py is import-able via `from conftest import _signal_dict`, but per Plan 13-02 LEARNING (conftest import path issue), inline the helper definition in each test file with a comment pointing to conftest as single source).

3. Run `pytest -x` — fix any cascade fail.

4. Final grep gate:
   ```bash
   grep -rn 'signals\[.[A-Z0-9_]\+.\]\s*=\s*-\?[0-9]\s*$' tests/
   # expected: zero matches (every site now uses _signal_dict(...))
   ```
  </action>
  <verify>
    <automated>pytest -x 2>&1 | tail -5 | grep -E "passed|failed"</automated>
  </verify>
  <done>
    - All 38 test sites refactored.
    - Final grep gate empty.
    - Full suite green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| state.json (legacy) → migrated state | Bare-int rows must be silently promoted, not crash the renderer |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-27-09-01 | DoS | Legacy state.json with bare-int signals reaches renderer after migrator removed but renderer cleanup landed → AttributeError on render | mitigate | Migrator runs at load_state — no bare-int reaches renderer post-load. Tests cover the migration. |
| T-27-09-02 | Tampering | N/A | accept | — |
</threat_model>

<verification>
```
pytest tests/test_signal_shape_migration.py -x -v
grep -n 'isinstance.*int' dashboard_renderer/components/signals.py
# expected: zero matches
grep -rn 'signals\[.[A-Z0-9_]\+.\]\s*=\s*-\?[0-9]\s*$' tests/
# expected: zero matches
pytest -x   # full suite
```
</verification>

<success_criteria>
- Schema bumped + migrator registered + chain contiguity holds.
- Renderer defensive branch removed.
- 38 test sites refactored to dict shape.
- 5 new migration tests green.
- Full suite green.
</success_criteria>

<output>
Create `27-09-SUMMARY.md` with: schema version bump (N→N+1), migrator code, list of refactored test files + per-file count of replacements, before/after grep counts.
</output>
