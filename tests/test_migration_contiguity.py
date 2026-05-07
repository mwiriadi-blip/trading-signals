'''Phase 27 Plan 07 — schema-migration chain contiguity regression tests.

Behavior under test (M1 review-fix: BEHAVIORAL, not source-position):
  - Importing/reloading state_manager succeeds — proves the in-tree
    MIGRATIONS dict is contiguous from 1 → STATE_SCHEMA_VERSION at
    module-load time (defensive guard runs at import).
  - Calling _assert_migration_chain_contiguous with a fake MIGRATIONS
    dict that has a gap raises RuntimeError naming the missing key(s).
  - load_state on a valid state file fails BEFORE returning when the
    migration chain has a gap (the assertion runs at load_state entry,
    not just at import). This is the load-time behavior gate that
    replaces the brittle "last line of module is ..." source-position
    check (M1).
  - Tracing demonstrates _assert_migration_chain_contiguous fires
    EARLY in load_state — before the migration walk would consume
    state — by observing that the RuntimeError raises pre-migration.
'''
import importlib
import json

import pytest

import state_manager


class TestMigrationChainContiguity:
  '''All four tests target observable BEHAVIOR, not source positions.'''

  def test_migration_chain_contiguous_passes_at_import(self):
    # Reloading the module re-runs every module-level statement, including
    # the bottom-of-module _assert_migration_chain_contiguous() call. If
    # the in-tree MIGRATIONS dict has any gap, this reload would raise
    # RuntimeError instead of returning a module object.
    reloaded = importlib.reload(state_manager)
    assert reloaded is state_manager
    # Sanity: in-tree chain has every key 2..STATE_SCHEMA_VERSION present.
    for v in range(2, state_manager.STATE_SCHEMA_VERSION + 1):
      assert v in state_manager.MIGRATIONS, (
        f'in-tree MIGRATIONS dict is missing key {v}'
      )

  def test_migration_chain_with_gap_raises_at_helper_call(self, monkeypatch):
    # Construct a fake MIGRATIONS dict missing key 5 with STATE_SCHEMA_VERSION=8.
    fake_migrations = {
      1: lambda s: s,
      2: lambda s: s,
      3: lambda s: s,
      4: lambda s: s,
      # 5 deliberately omitted
      6: lambda s: s,
      7: lambda s: s,
      8: lambda s: s,
    }
    monkeypatch.setattr(state_manager, 'MIGRATIONS', fake_migrations)
    monkeypatch.setattr(state_manager, 'STATE_SCHEMA_VERSION', 8)
    with pytest.raises(RuntimeError, match=r'missing keys \[5\]'):
      state_manager._assert_migration_chain_contiguous()

  def test_load_state_fails_on_non_contiguous_chain(self, monkeypatch, tmp_path):
    '''Behavioral test (review-fix M1): load_state must call the contiguity
    assertion at entry, so a state file load FAILS on a gapped chain — not
    just module import.
    '''
    # Place a valid (parseable) state.json on disk.
    fake_state_path = tmp_path / 'state.json'
    fake_state_path.write_text(json.dumps({
      'schema_version': 1,
      'account': 1000.0,
    }))
    # Inject a chain with a gap: missing key 3, STATE_SCHEMA_VERSION=4.
    fake_migrations = {
      1: lambda s: s,
      2: lambda s: s,
      # 3 deliberately omitted
      4: lambda s: s,
    }
    monkeypatch.setattr(state_manager, 'MIGRATIONS', fake_migrations)
    monkeypatch.setattr(state_manager, 'STATE_SCHEMA_VERSION', 4)
    with pytest.raises(RuntimeError, match=r'missing keys \[3\]'):
      state_manager.load_state(path=fake_state_path)

  def test_migration_chain_called_at_load_state_entry(self, monkeypatch, tmp_path):
    '''Behavioral guard that the contiguity check fires EARLY in load_state
    — before the migration walk would consume state. We assert the
    RuntimeError raises and that the migration callable was NEVER invoked
    (proving the assertion runs at entry, not interleaved with migrate).
    '''
    fake_state_path = tmp_path / 'state.json'
    fake_state_path.write_text(json.dumps({
      'schema_version': 1,
      'account': 1000.0,
    }))
    invocations: list[int] = []

    def _track(version: int):
      def _migrator(s: dict) -> dict:
        invocations.append(version)
        return s
      return _migrator

    # Gap at key 2 — STATE_SCHEMA_VERSION=3 expects keys [2,3]; only 3 present.
    fake_migrations = {
      1: lambda s: s,
      # 2 deliberately omitted
      3: _track(3),
    }
    monkeypatch.setattr(state_manager, 'MIGRATIONS', fake_migrations)
    monkeypatch.setattr(state_manager, 'STATE_SCHEMA_VERSION', 3)
    with pytest.raises(RuntimeError, match=r'missing keys \[2\]'):
      state_manager.load_state(path=fake_state_path)
    assert invocations == [], (
      f'expected no migrators invoked (assertion fires before migrate); got {invocations}'
    )
