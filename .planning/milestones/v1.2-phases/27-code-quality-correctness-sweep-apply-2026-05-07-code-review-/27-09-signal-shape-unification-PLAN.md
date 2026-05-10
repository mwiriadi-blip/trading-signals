---
phase: 27
plan: 09
type: execute
wave: 2B
parallel: false
depends_on:
  - 27-01-decimal-money-math-PLAN.md  # <!-- review-fix: agreed-1 — schema bump must follow Decimal migration -->
  - 27-07-naive-datetime-and-migration-contiguity-PLAN.md  # <!-- review-fix: agreed-1 — _assert_migration_chain_contiguous must exist -->
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
    - "All 38+ test sites that seeded `state['signals']['SPI200'] = 0` migrated to dict shape."
    - "_migrate_v9_to_v10 promotes any bare-int signals row found at load time (chain reaches v10 because 27-01 lands first as v9)."
    - "STATE_SCHEMA_VERSION bumped to 10 (deterministic — Plan 27-01 lands first per Wave 1B → 2B sequencing)."
  artifacts:
    - path: state_manager.py
      provides: "_migrate_v9_to_v10 promoting bare-int signals to dict"
      contains: "_migrate_v9_to_v10"
    - path: dashboard_renderer/components/signals.py
      provides: "defensive int branch removed"
      contains: "signals.py"
  key_links:
    - from: "_migrate_v9_to_v10"
      to: "_assert_migration_chain_contiguous"
      via: "newly registered key"
      pattern: "_MIGRATIONS\\["
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `2` → `2B`; depends_on=[27-01, 27-07] explicit. Sequencing now deterministic: 27-01 (v9) → this plan (v10).
- [x] OpenCode LOW (schema version after 27-01) — confirmed: schema reaches v10 here (27-01 lands first as v9 per Wave 1B → 2B sequencing).
- [x] M1 (brittle implementation tests) — kept behavioral tests (renderer fails-loudly on bare-int post-migration; chain contiguity holds). No source-position assertions.
- [x] M2 (doc rule) — SUMMARY artifact stays inside `.planning/phases/27-.../`.

<objective>
Drop bare-int signal back-compat per Phase 26 DEBT.md R5. State shape `state['signals'][market_id]` is always a dict. Migrate any legacy bare-int rows at load time. Delete the renderer's defensive `isinstance(record, int)` branch (signals.py:35-39). Update all 38+ test sites to use dict shape.

Sequenced AFTER 27-01 (schema version bump to v9) and 27-07 (migration-chain contiguity assert), so this plan bumps to v10 in a clean, contiguous chain.

Purpose: shape unification (review item #11). Phase 26 DEBT.md R5 explicitly flags this.
Output: schema bump v9→v10 + migration + 38-site test refactor + renderer cleanup.
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
#     'strategy_version': 'v1.2.0',
#     'as_of': '2026-05-07',
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
#   elif isinstance(sig_entry, int):
#     direction = sig_entry
#     version = 'unknown'
# DELETE this elif. After migration, only dict shape reaches the renderer.
#
# Schema bump (deterministic per agreed-1 sequencing):
#   STATE_SCHEMA_VERSION: 9 → 10
#   Register _migrate_v9_to_v10:
#     for k, v in s.get('signals', {}).items():
#       if isinstance(v, int):
#         s['signals'][k] = {'direction': v, 'strategy_version': STRATEGY_VERSION, 'as_of': None}
#
# 38 test sites — discover via:
#   grep -rn "signals\['[A-Z0-9_]\+'\] = [-0-9]" tests/
# Mechanical replacement per site:
#   from old:  state['signals']['SPI200'] = 0
#   to new:    state['signals']['SPI200'] = _signal_dict(0)
# Helper in tests/conftest.py:
#   def _signal_dict(direction: int, version: str = STRATEGY_VERSION, as_of: str = '2026-05-07') -> dict:
#     return {'direction': direction, 'strategy_version': version, 'as_of': as_of}
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: _migrate_v9_to_v10 + schema bump + renderer cleanup</name>
  <read_first>
    - state_manager.py lines 232-310 (existing migrators, _MIGRATIONS dict — post 27-01 has key 9)
    - dashboard_renderer/components/signals.py (full)
    - tests/conftest.py
  </read_first>
  <behavior>
    - test_migrate_v9_to_v10_promotes_bare_int_to_dict: _migrate_v9_to_v10({signals: {SPI200: 0, AUDUSD: 1}}) returns dict-shaped signals.
    - test_migrate_idempotent_on_already_dict: row already dict-shaped passes through unchanged.
    - test_renderer_no_isinstance_int_branch: read signals.py source; `isinstance(.*int)` does NOT appear (regex grep).
    - test_renderer_renders_dict_signal: pass a dict-shaped signal entry through render; assert correct HTML.
    - test_chain_contiguity_holds_after_v10_bump: import state_manager — _assert_migration_chain_contiguous succeeds with chain 1→10.
  </behavior>
  <action>
1. **state_manager.py:** read current STATE_SCHEMA_VERSION (post 27-01 = 9). Bump to 10.

2. Add `_migrate_v9_to_v10` per <interfaces>. Register `10: _migrate_v9_to_v10` in _MIGRATIONS.

3. **dashboard_renderer/components/signals.py:** delete the `elif isinstance(sig_entry, int):` block (lines 35-39). After deletion, the function expects dict shape.

4. **Add _signal_dict helper in tests/conftest.py.**

5. **tests/test_signal_shape_migration.py (NEW):** 5 tests per behavior block.
  </action>
  <verify>
    <automated>pytest tests/test_signal_shape_migration.py -x -v</automated>
  </verify>
  <done>
    - Migrator registered; chain contiguity check green.
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
  </read_first>
  <action>
1. Discover all test sites:
   ```bash
   grep -rn 'signals\[.[A-Z0-9_]\+.\]\s*=\s*-\?[0-9]' tests/
   ```
   Capture file:line:content list. Expected ~38 matches.

2. Mechanical substitution per site:
   ```python
   # before
   state['signals']['SPI200'] = 0
   # after
   state['signals']['SPI200'] = _signal_dict(0)
   ```
   Inline `_signal_dict` definition in each test file with comment pointing to conftest as single source (avoiding the conftest-import LEARNING from Plan 13-02).

3. Run `pytest -x` — fix any cascade.

4. Final grep gate:
   ```bash
   grep -rn 'signals\[.[A-Z0-9_]\+.\]\s*=\s*-\?[0-9]\s*$' tests/
   # expected: zero matches
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
| T-27-09-01 | DoS | Legacy state.json with bare-int signals + renderer cleanup landed → AttributeError | mitigate | Migrator runs at load_state. Tests cover migration. |
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
- Schema bumped v9→v10; migrator registered; chain contiguity holds.
- Renderer defensive branch removed.
- 38 test sites refactored.
- 5 migration tests green.
- Full suite green.
</success_criteria>

<output>
Create `27-09-SUMMARY.md` with: schema version bump v9→v10, migrator code, refactored test files + per-file replacement count, before/after grep counts.
</output>
