'''Phase 33 Plan 02: v11→v12 round-trip + validation test suite.

Tests:
  TestV12RoundTrip      — 5 parametrized fixtures, forward-only lossless check
  TestStateV12Schema    — full migration chain + Pydantic StateV12 validation
  TestV12AutoBackup     — backup fires for pre-v12 state, not for v12 state
  TestV12Contiguity     — MIGRATIONS chain 1..12, STATE_SCHEMA_VERSION == 12
'''
import json
import warnings
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture file paths
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).parent / 'fixtures'

FIXTURE_FILES = {
  'empty':                FIXTURES_DIR / 'state_v11_empty.json',
  'max_trade_log':        FIXTURES_DIR / 'state_v11_max_trade_log.json',
  'mid_pyramid':          FIXTURES_DIR / 'state_v11_mid_pyramid.json',
  'mid_alert_approaching': FIXTURES_DIR / 'state_v11_mid_alert_approaching.json',
  'naive_datetime':       FIXTURES_DIR / 'state_v11_naive_datetime.json',
}


def _load_fixture(name: str) -> dict:
  path = FIXTURE_FILES[name]
  with open(path) as f:
    return json.load(f)


# ---------------------------------------------------------------------------
# TestV12RoundTrip
# ---------------------------------------------------------------------------
class TestV12RoundTrip:
  '''Forward-only lossless round-trip: every v11 field that maps to v12
  is present with identical value at the correct v12 path.

  Asserts 10 invariants per fixture:
    1. result['schema_version'] == 11 (migrator does NOT bump version)
    2. result['users'][_ADMIN_UID]['account'] == fixture['account']
    3. result['users'][_ADMIN_UID]['trade_log'] == fixture['trade_log']
    4. result['users'][_ADMIN_UID]['paper_trades'] == fixture.get('paper_trades', [])
    5. result['users'][_ADMIN_UID]['equity_history'] == fixture['equity_history']
    6. result['users'][_ADMIN_UID]['contracts'] == fixture['contracts']
    7. result['users'][_ADMIN_UID]['positions'] == fixture['positions']
    8. result['admin_user_id'] == 'u_admin_marc'
    9. 'account' NOT in result (top-level removed)
    10. 'trade_log' NOT in result (top-level removed)
  '''

  @pytest.mark.parametrize('fixture_name', [
    'empty',
    'max_trade_log',
    'mid_pyramid',
    'mid_alert_approaching',
    'naive_datetime',
  ])
  def test_round_trip(self, fixture_name: str) -> None:
    '''Forward-only lossless: v11 field values preserved at v12 user-bucket path.'''
    from state_manager import _migrate_v11_to_v12
    from state_manager.migrations import _ADMIN_UID

    fixture = _load_fixture(fixture_name)
    result = _migrate_v11_to_v12(dict(fixture))
    user = result['users'][_ADMIN_UID]

    # Invariant 1: migrator does NOT bump schema_version
    assert result['schema_version'] == 11, (
      f'[{fixture_name}] migrator must not bump schema_version; '
      f'got {result["schema_version"]!r}'
    )

    # Invariant 2: account preserved
    assert user['account'] == fixture['account'], (
      f'[{fixture_name}] account mismatch: {user["account"]!r} != {fixture["account"]!r}'
    )

    # Invariant 3: trade_log preserved
    assert user['trade_log'] == fixture['trade_log'], (
      f'[{fixture_name}] trade_log mismatch'
    )

    # Invariant 4: paper_trades preserved (default empty list)
    expected_pt = fixture.get('paper_trades', [])
    assert user['paper_trades'] == expected_pt, (
      f'[{fixture_name}] paper_trades mismatch'
    )

    # Invariant 5: equity_history preserved
    assert user['equity_history'] == fixture['equity_history'], (
      f'[{fixture_name}] equity_history mismatch'
    )

    # Invariant 6: contracts preserved
    assert user['contracts'] == fixture['contracts'], (
      f'[{fixture_name}] contracts mismatch'
    )

    # Invariant 7: positions preserved
    assert user['positions'] == fixture['positions'], (
      f'[{fixture_name}] positions mismatch'
    )

    # Invariant 8: admin_user_id set to _ADMIN_UID
    assert result['admin_user_id'] == _ADMIN_UID, (
      f'[{fixture_name}] admin_user_id must be {_ADMIN_UID!r}; '
      f'got {result.get("admin_user_id")!r}'
    )

    # Invariant 9: 'account' NOT at top-level
    assert 'account' not in result, (
      f'[{fixture_name}] "account" must NOT be at top-level after v12 migration'
    )

    # Invariant 10: 'trade_log' NOT at top-level
    assert 'trade_log' not in result, (
      f'[{fixture_name}] "trade_log" must NOT be at top-level after v12 migration'
    )


# ---------------------------------------------------------------------------
# TestStateV12Schema
# ---------------------------------------------------------------------------
class TestStateV12Schema:
  '''Full migration chain + Pydantic StateV12 structural validation.

  For each fixture: run _migrate (full chain from v11 → v12 + schema_version bump),
  then StateV12.model_validate(migrated) — must not raise.
  '''

  @pytest.mark.parametrize('fixture_name', [
    'empty',
    'max_trade_log',
    'mid_pyramid',
    'mid_alert_approaching',
    'naive_datetime',
  ])
  def test_pydantic_validation_passes(self, fixture_name: str) -> None:
    '''Full migration chain produces a StateV12-valid result.'''
    from state_manager import _migrate
    from state_manager.validation import StateV12

    fixture = _load_fixture(fixture_name)
    # Suppress DeprecationWarning from naive-datetime coercion shim (valid for naive_datetime fixture)
    with warnings.catch_warnings():
      warnings.simplefilter('ignore', DeprecationWarning)
      migrated = _migrate(dict(fixture))

    # StateV12.model_validate must not raise
    try:
      StateV12.model_validate(migrated)
    except Exception as exc:
      pytest.fail(
        f'[{fixture_name}] StateV12.model_validate raised: {exc!r}\n'
        f'migrated keys: {list(migrated.keys())}'
      )


# ---------------------------------------------------------------------------
# TestV12AutoBackup
# ---------------------------------------------------------------------------
class TestV12AutoBackup:
  '''load_state creates a .v11-backup-* file when schema_version < 12;
  does NOT create one when schema_version == 12.'''

  def test_backup_created_for_pre_v12_state(self, tmp_path: Path) -> None:
    '''A v11-shaped JSON triggers shutil.copy2 backup on load_state().'''
    from state_manager import load_state
    from state_manager.migrations import _ADMIN_UID

    # Write a minimal v11 state to tmp_path
    state_file = tmp_path / 'state.json'
    v11_state = {
      'schema_version': 11,
      'account': 10000.0,
      'initial_account': 10000.0,
      'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {},
      'trade_log': [],
      'equity_history': [],
      'warnings': [],
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
      'paper_trades': [],
      'markets': {
        'SPI200': {
          'symbol': '^AXJO',
          'label': 'SPI 200',
          'multiplier': 25,
          'tick': 1.0,
          'currency': 'AUD',
          'rt_cost': 6.0,
          'contract_type': 'future',
          'financing_rate_annual_pct': 0.0,
        },
        'AUDUSD': {
          'symbol': 'AUDUSD=X',
          'label': 'AUD/USD',
          'multiplier': 100000,
          'tick': 0.0001,
          'currency': 'AUD',
          'rt_cost': 5.0,
          'contract_type': 'cfd',
          'financing_rate_annual_pct': 3.0,
        },
      },
      'strategy_settings': {
        'SPI200': {'momentum_votes_required': 2, 'adx_threshold': 25},
        'AUDUSD': {'momentum_votes_required': 2, 'adx_threshold': 25},
      },
    }
    state_file.write_text(json.dumps(v11_state))

    # load_state should trigger the backup
    with warnings.catch_warnings():
      warnings.simplefilter('ignore', DeprecationWarning)
      load_state(path=state_file)

    # Assert at least one .v11-backup-* file exists
    backup_files = list(tmp_path.glob(f'{state_file.name}.v11-backup-*'))
    assert len(backup_files) >= 1, (
      f'Expected at least one .v11-backup-* file in {tmp_path}; '
      f'found: {[f.name for f in tmp_path.iterdir()]}'
    )

  def test_no_backup_for_v12_state(self, tmp_path: Path) -> None:
    '''A v12-shaped JSON does NOT trigger backup on load_state().'''
    from state_manager import load_state
    from state_manager.migrations import _ADMIN_UID
    from system_params import STATE_SCHEMA_VERSION

    # Write a valid v12 state directly (no migration needed)
    state_file = tmp_path / 'state.json'
    v12_state = {
      'schema_version': STATE_SCHEMA_VERSION,  # 12
      'last_run': '2026-04-30',
      'signals': {},
      'warnings': [],
      'markets': {
        'SPI200': {
          'symbol': '^AXJO',
          'label': 'SPI 200',
          'multiplier': 25,
          'tick': 1.0,
          'currency': 'AUD',
          'rt_cost': 6.0,
          'contract_type': 'future',
          'financing_rate_annual_pct': 0.0,
        },
        'AUDUSD': {
          'symbol': 'AUDUSD=X',
          'label': 'AUD/USD',
          'multiplier': 100000,
          'tick': 0.0001,
          'currency': 'AUD',
          'rt_cost': 5.0,
          'contract_type': 'cfd',
          'financing_rate_annual_pct': 3.0,
        },
      },
      'strategy_settings': {
        'SPI200': {'momentum_votes_required': 2, 'adx_threshold': 25},
        'AUDUSD': {'momentum_votes_required': 2, 'adx_threshold': 25},
      },
      'admin_user_id': _ADMIN_UID,
      'users': {
        _ADMIN_UID: {
          'account': 10000.0,
          'initial_account': 10000.0,
          'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
          'positions': {'SPI200': None, 'AUDUSD': None},
          'trade_log': [],
          'equity_history': [],
          'paper_trades': [],
          'ui_prefs': {'tour_completed': True},
        },
      },
    }
    state_file.write_text(json.dumps(v12_state))

    # Snapshot existing backup files before load
    before = set(tmp_path.glob(f'{state_file.name}.v11-backup-*'))

    load_state(path=state_file)

    # No new backup files should appear
    after = set(tmp_path.glob(f'{state_file.name}.v11-backup-*'))
    new_backups = after - before
    assert len(new_backups) == 0, (
      f'Expected no new backup files for already-v12 state; '
      f'found new: {[f.name for f in new_backups]}'
    )


# ---------------------------------------------------------------------------
# TestV12Contiguity
# ---------------------------------------------------------------------------
class TestV12Contiguity:
  '''Migration chain 1..12 is contiguous; STATE_SCHEMA_VERSION == 12.'''

  def test_migration_chain_contiguous(self) -> None:
    '''_assert_migration_chain_contiguous() does not raise.'''
    from state_manager.migrations import _assert_migration_chain_contiguous
    # Must not raise
    _assert_migration_chain_contiguous()

  def test_state_schema_version_is_12(self) -> None:
    '''STATE_SCHEMA_VERSION constant is 12.'''
    from system_params import STATE_SCHEMA_VERSION
    assert STATE_SCHEMA_VERSION == 12, (
      f'Expected STATE_SCHEMA_VERSION == 12; got {STATE_SCHEMA_VERSION!r}'
    )

  def test_migrations_keys_1_to_12_no_gaps(self) -> None:
    '''MIGRATIONS dict has keys 1..12 with no gaps.'''
    from state_manager.migrations import MIGRATIONS
    from system_params import STATE_SCHEMA_VERSION

    expected = set(range(1, STATE_SCHEMA_VERSION + 1))  # {1, 2, ..., 12}
    actual = set(MIGRATIONS.keys())
    assert expected == actual, (
      f'MIGRATIONS keys mismatch.\n'
      f'  Expected: {sorted(expected)}\n'
      f'  Got:      {sorted(actual)}\n'
      f'  Missing:  {sorted(expected - actual)}\n'
      f'  Extra:    {sorted(actual - expected)}'
    )
