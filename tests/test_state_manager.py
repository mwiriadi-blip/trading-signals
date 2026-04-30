'''Phase 3 test suite: state persistence, atomic writes, corruption recovery,
trade recording, equity history, reset, warnings, and schema migration.

Organized into classes per D-13 (one class per concern dimension):
  TestLoadSave, TestAtomicity, TestCorruptionRecovery, TestRecordTrade,
  TestEquityHistory, TestReset, TestWarnings, TestSchemaVersion.

All tests use tmp_path (pytest built-in) for isolated state files — never
touch the real ./state.json. Clock-dependent functions accept now= injection
so tests are deterministic without pytest-freezer.

Wave 0 (this commit): empty skeletons with class docstrings and _make_trade
helper. Waves 1-3 fill in the test methods per the wave annotation in each
class docstring.
'''
import json  # noqa: F401 — used in Wave 1/2 TestLoadSave/TestCorruptionRecovery
import os  # noqa: F401 — used in Wave 1 TestAtomicity
from datetime import UTC, datetime, timezone  # noqa: F401 — used in Wave 1/2 clock injection
from pathlib import Path
from unittest.mock import patch  # noqa: F401 — used in Wave 1 TestAtomicity

import pytest  # noqa: F401 — used across Waves 1/2/3 for raises / parametrize

from state_manager import (
  MIGRATIONS,  # noqa: F401 — used in Wave 1 TestSchemaVersion
  _migrate,  # noqa: F401 — used in Phase 8 TestMigrateV2Backfill
  _validate_loaded_state,  # noqa: F401 — used in Phase 8 tests
  append_warning,  # noqa: F401 — used in Wave 2 TestWarnings
  clear_warnings,  # noqa: F401 — used in Phase 8 TestClearWarnings
  load_state,  # noqa: F401 — used in Waves 1/2 TestLoadSave/TestCorruptionRecovery
  record_trade,  # noqa: F401 — used in Wave 3 TestRecordTrade
  reset_state,  # noqa: F401 — used in Wave 2 TestReset
  save_state,  # noqa: F401 — used in Wave 1 TestLoadSave/TestAtomicity
  update_equity_history,  # noqa: F401 — used in Wave 3 TestEquityHistory
)
from system_params import (
  AUDUSD_CONTRACTS,  # noqa: F401 — used in Phase 8 TestLoadStateResolvesContracts
  INITIAL_ACCOUNT,  # noqa: F401 — used in Wave 2 TestReset
  MAX_WARNINGS,  # noqa: F401 — used in Wave 2 TestWarnings
  SPI_CONTRACTS,  # noqa: F401 — used in Phase 8 TestLoadStateResolvesContracts
  STATE_FILE,  # noqa: F401 — used in Wave 1 TestLoadSave default path
  STATE_SCHEMA_VERSION,  # noqa: F401 — used in Wave 1 TestSchemaVersion
  _DEFAULT_AUDUSD_LABEL,  # noqa: F401 — used in Phase 8 tests
  _DEFAULT_SPI_LABEL,  # noqa: F401 — used in Phase 8 tests
)

# =========================================================================
# Module-level path constants (mirrors test_signal_engine.py SIGNAL_ENGINE_PATH pattern)
# =========================================================================

STATE_MANAGER_PATH = Path('state_manager.py')
TEST_STATE_MANAGER_PATH = Path('tests/test_state_manager.py')

# =========================================================================
# Test fixture helpers
# =========================================================================

def _make_trade(
  instrument: str = 'SPI200',
  direction: str = 'LONG',
  entry_price: float = 7000.0,
  exit_price: float = 7100.0,
  n_contracts: int = 2,
  gross_pnl: float = 1000.0,
  cost_aud: float = 6.0,
  multiplier: float = 5.0,
  exit_reason: str = 'flat_signal',
  entry_date: str = '2026-01-02',
  exit_date: str = '2026-01-09',
) -> dict:
  '''Build a trade dict with sensible defaults. All required fields per D-15.

  gross_pnl is the RAW price-delta P&L (D-14 contract):
    (exit_price - entry_price) * n_contracts * multiplier  for LONG
    (entry_price - exit_price) * n_contracts * multiplier  for SHORT
  It is NOT Phase 2's ClosedTrade.realised_pnl (which already has the
  closing cost deducted). See state_manager.record_trade docstring for the
  Phase 4 boundary warning.
  '''
  return {
    'instrument': instrument,
    'direction': direction,
    'entry_price': entry_price,
    'exit_price': exit_price,
    'n_contracts': n_contracts,
    'gross_pnl': gross_pnl,
    'cost_aud': cost_aud,
    'multiplier': multiplier,
    'exit_reason': exit_reason,
    'entry_date': entry_date,
    'exit_date': exit_date,
  }

# =========================================================================
# Test classes — one per concern dimension (D-13)
# =========================================================================

class TestLoadSave:
  '''STATE-01 / STATE-02: load_state and save_state round-trip + atomic write success path.

  All tests use tmp_path to avoid touching the real ./state.json.
  Wave 1 fills this in.
  '''

  def test_save_state_creates_readable_file(self, tmp_path) -> None:
    '''STATE-02: save_state writes state.json; file is parseable JSON; contents match input.'''
    path = tmp_path / 'state.json'
    state = {
      'schema_version': STATE_SCHEMA_VERSION,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [],
      'equity_history': [],
      'warnings': [],
    }
    save_state(state, path=path)
    assert path.exists(), 'state.json must exist after save_state'
    loaded = json.loads(path.read_text())
    assert loaded == state, 'JSON round-trip must preserve state exactly'

  def test_save_state_is_deterministic_byte_identical(self, tmp_path) -> None:
    '''Claude's Discretion: sort_keys=True + indent=2 produces byte-identical output.'''
    path = tmp_path / 'state.json'
    state = {
      'schema_version': 1, 'account': 100_000.0, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    save_state(state, path=path)
    first_bytes = path.read_bytes()
    save_state(state, path=path)
    second_bytes = path.read_bytes()
    assert first_bytes == second_bytes, 'sort_keys must produce deterministic output'
    # indent=2 evidence: state.json contains a 2-space-indented line
    assert b'\n  ' in first_bytes, 'output must use 2-space indent'

  def test_save_state_raises_on_nan(self, tmp_path) -> None:
    '''Pitfall 6 / Claude's Discretion: allow_nan=False surfaces NaN as ValueError.'''
    path = tmp_path / 'state.json'
    state = {
      'schema_version': 1, 'account': float('nan'), 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    with pytest.raises(ValueError):
      save_state(state, path=path)

  def test_load_state_missing_file_returns_fresh_shape(self, tmp_path) -> None:
    '''STATE-01 + B-3: missing state.json returns dict with all 8 top-level keys at default values
    AND does NOT create the file (no side-effect on read).
    '''
    path = tmp_path / 'state.json'
    assert not path.exists()
    state = load_state(path=path)
    # All 8 STATE-01 top-level keys present
    for key in ('schema_version', 'account', 'last_run', 'positions',
                'signals', 'trade_log', 'equity_history', 'warnings'):
      assert key in state, f'STATE-01: missing top-level key {key!r}'
    # Default values per D-01 / D-03 / STATE-07
    assert state['schema_version'] == STATE_SCHEMA_VERSION
    assert state['account'] == INITIAL_ACCOUNT
    assert state['last_run'] is None
    assert state['positions'] == {'SPI200': None, 'AUDUSD': None}, 'D-01: None when flat'
    assert state['signals'] == {'SPI200': 0, 'AUDUSD': 0}, 'D-03: FLAT=0 init'
    assert state['trade_log'] == []
    assert state['equity_history'] == []
    assert state['warnings'] == []
    # B-3: no side-effect on read — load_state on missing path must NOT create the file.
    # Orchestrator (Phase 4) must explicitly call save_state to materialize state.json.
    assert not path.exists(), (
      'B-3: load_state on missing path must NOT create state.json; '
      'orchestrator owns file materialization via explicit save_state(state)'
    )

  def test_save_load_round_trip_preserves_state(self, tmp_path) -> None:
    '''STATE-01 / STATE-02: a fully-populated state survives save → load bit-for-bit.'''
    path = tmp_path / 'state.json'
    state = {
      'schema_version': STATE_SCHEMA_VERSION,
      'account': 99000.5,
      'last_run': '2026-04-21',
      'positions': {
        'SPI200': {
          'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-01-02',
          'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 7100.0,
          'trough_price': None, 'atr_entry': 53.0,
        },
        'AUDUSD': None,
      },
      'signals': {'SPI200': 1, 'AUDUSD': -1},
      'trade_log': [
        {'instrument': 'AUDUSD', 'direction': 'SHORT', 'net_pnl': 250.0,
         'entry_date': '2026-03-01', 'exit_date': '2026-03-15'},
      ],
      'equity_history': [
        {'date': '2026-04-19', 'equity': 99500.0},
        {'date': '2026-04-20', 'equity': 99750.0},
        {'date': '2026-04-21', 'equity': 99000.5},
      ],
      'warnings': [
        {'date': '2026-04-20', 'source': 'sizing_engine', 'message': 'size=0: ...'},
      ],
      # Phase 8 (v2 schema): CONF-01 + CONF-02 top-level keys required by
      # _validate_loaded_state. Round-trip equality comparison below
      # ignores the runtime-only _resolved_contracts key (load_state
      # materialises it after migration; save_state strips it before dump).
      'initial_account': INITIAL_ACCOUNT,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
    }
    save_state(state, path=path)
    loaded = load_state(path=path)
    # Phase 8: load_state materialises _resolved_contracts (runtime-only
    # per D-14); strip before equality to compare persisted shape only.
    loaded_persisted = {k: v for k, v in loaded.items() if not k.startswith('_')}
    assert loaded_persisted == state, 'round-trip must preserve every field including nested dicts/lists'

class TestAtomicity:
  '''STATE-02 / D-08 (amended by D-17): crash simulation + post-replace fsync ordering proof.

  Patch target is `state_manager.os.replace` so the mock intercepts the
  exact call made inside save_state's _atomic_write helper.
  Wave 1 fills this in.
  '''

  def test_crash_on_os_replace_leaves_original_intact(self, tmp_path) -> None:
    '''STATE-02: if os.replace raises mid-write, state.json is byte-identical to original.'''
    path = tmp_path / 'state.json'
    original_state = {
      'schema_version': 1, 'account': 99999.0, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    save_state(original_state, path=path)
    original_bytes = path.read_bytes()

    new_state = dict(original_state)
    new_state['account'] = 50000.0

    with patch('state_manager.os.replace', side_effect=OSError('disk full')):
      with pytest.raises(OSError, match='disk full'):
        save_state(new_state, path=path)

    assert path.read_bytes() == original_bytes, (
      'STATE-02: original state.json must be byte-identical after failed os.replace'
    )

  def test_tempfile_cleaned_up_on_failure(self, tmp_path) -> None:
    '''Pitfall 1: try/finally cleanup unlinks the tempfile when save_state raises.'''
    path = tmp_path / 'state.json'
    save_state({
      'schema_version': 1, 'account': 100_000.0, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }, path=path)

    with patch('state_manager.os.replace', side_effect=OSError('boom')):
      with pytest.raises(OSError):
        save_state({
          'schema_version': 1, 'account': 50_000.0, 'last_run': None,
          'positions': {'SPI200': None, 'AUDUSD': None},
          'signals': {'SPI200': 0, 'AUDUSD': 0},
          'trade_log': [], 'equity_history': [], 'warnings': [],
        }, path=path)

    # After failure, tmp_path contains only state.json — no leftover .tmp files
    leftover_tmps = list(tmp_path.glob('*.tmp'))
    assert leftover_tmps == [], (
      f'Pitfall 1: tempfile cleanup failed; found leftover .tmp files: {leftover_tmps}'
    )

  def test_save_state_on_clean_disk_leaves_no_tempfile(self, tmp_path) -> None:
    '''Successful save: only state.json on disk; no leftover .tmp files.'''
    path = tmp_path / 'state.json'
    save_state({
      'schema_version': 1, 'account': 100_000.0, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }, path=path)
    leftover_tmps = list(tmp_path.glob('*.tmp'))
    assert leftover_tmps == [], (
      f'success path must not leave tempfiles; found: {leftover_tmps}'
    )
    assert path.exists()

  def test_atomic_write_fsyncs_parent_dir_after_os_replace(self, tmp_path) -> None:
    '''D-17 (amends D-08): post-replace fsync ordering for durability.

    The canonical durable-write idiom is:
      write -> flush -> fsync(file) -> close -> os.replace -> fsync(parent dir)

    The parent-dir fsync MUST come AFTER os.replace because its purpose is
    to make the rename itself durable on disk. fsync'ing before the replace
    only persists the not-yet-renamed temp file's directory entry, leaving
    the rename in the OS write cache (and thus lost if power fails between
    replace and the next implicit dir flush).

    This test is the structural enforcement of D-17. It will fail if
    _atomic_write is reverted to RESEARCH.md §Pattern 1's pre-replace
    ordering (which is what the original Wave 1 plan documented before the
    2026-04-21 reviews-revision pass).

    Mechanism: patch both os.replace and os.fsync on the state_manager
    module via a single MagicMock parent so all child-call records share
    an ordered call list. Patch os.open to return a sentinel _DIR_FD so we
    can distinguish the parent-dir fsync from the file fsync in the call
    record.
    '''
    from unittest.mock import MagicMock
    path = tmp_path / 'state.json'
    state = {
      'schema_version': 1, 'account': 100_000.0, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }

    # Real implementations to call through to (we ONLY want to record order).
    real_replace = os.replace
    real_fsync = os.fsync
    real_open = os.open
    real_close = os.close
    _DIR_FD = 99999  # sentinel returned by patched os.open for the parent dir

    parent_mock = MagicMock()

    def recording_replace(*args, **kwargs):
      parent_mock.os_replace(*args, **kwargs)
      return real_replace(*args, **kwargs)

    def recording_fsync(fd, *args, **kwargs):
      # Tag the call so we can tell file-fd from dir-fd in the order record
      if fd == _DIR_FD:
        parent_mock.os_fsync_dir(fd)
        return None  # the sentinel fd is fake — don't actually fsync it
      parent_mock.os_fsync_file(fd)
      return real_fsync(fd, *args, **kwargs)

    def recording_open(path_arg, flags, *args, **kwargs):
      # Return the sentinel fd ONLY for the parent dir open (read-only).
      # NamedTemporaryFile also calls os.open with write flags; those go
      # through to real_open. os.open accepts (path, flags, mode=0o777, *, dir_fd=None).
      if flags == os.O_RDONLY:
        parent_mock.os_open_dir(path_arg)
        return _DIR_FD
      return real_open(path_arg, flags, *args, **kwargs)

    def recording_close(fd, *args, **kwargs):
      if fd == _DIR_FD:
        parent_mock.os_close_dir(fd)
        return None
      return real_close(fd, *args, **kwargs)

    # Skip on non-POSIX — _atomic_write itself short-circuits the dir fsync there.
    if os.name != 'posix':
      pytest.skip('D-17 ordering only enforced on POSIX')

    with patch('state_manager.os.replace', side_effect=recording_replace), \
         patch('state_manager.os.fsync', side_effect=recording_fsync), \
         patch('state_manager.os.open', side_effect=recording_open), \
         patch('state_manager.os.close', side_effect=recording_close):
      save_state(state, path=path)

    # Extract the ordered list of call names recorded on the parent mock
    call_names = [c[0] for c in parent_mock.mock_calls]

    assert 'os_replace' in call_names, (
      f'D-17: os.replace must be called during save_state; not seen in {call_names}'
    )
    assert 'os_fsync_dir' in call_names, (
      f'D-17: parent-dir fsync must be called during save_state; not seen in {call_names}. '
      'On POSIX hosts the dir-fsync block must execute (POSIX guard already passed).'
    )

    replace_idx = call_names.index('os_replace')
    dir_fsync_idx = call_names.index('os_fsync_dir')
    assert replace_idx < dir_fsync_idx, (
      f'D-17: os.replace must precede parent-dir fsync; '
      f'os_replace at index {replace_idx}, os_fsync_dir at index {dir_fsync_idx}. '
      f'Full call order: {call_names}. '
      f'Reverted ordering (pre-replace dir fsync) does not make the rename durable.'
    )

class TestCorruptionRecovery:
  '''STATE-03 / D-05 / D-06 (amended by B-1 + B-2) / D-07 / D-18: JSONDecodeError
  triggers backup + reinit + warning; valid-but-incomplete JSON raises ValueError.

  Wave 2 fills this in.
  '''

  def test_corrupt_file_triggers_backup_and_reset(self, tmp_path) -> None:
    '''STATE-03 / D-05/D-06/D-07 + B-2: garbage bytes -> backup created (with
    microsecond suffix), fresh state returned.
    '''
    path = tmp_path / 'state.json'
    path.write_bytes(b'\x00\xff\x00not json')
    # Inject a microsecond-precision timestamp so we can predict the suffix
    fixed_now = datetime(2026, 4, 21, 9, 30, 45, 123456, tzinfo=UTC)

    state = load_state(path=path, now=fixed_now)

    # B-2: backup uses microsecond-precision timestamp ('%Y%m%dT%H%M%S_%fZ')
    # Expected basename: state.json.corrupt.20260421T093045_123456Z
    backups = list(tmp_path.glob('state.json.corrupt.20260421T093045_*Z'))
    assert len(backups) == 1, (
      f'D-06 + B-2: expected 1 backup matching microsecond pattern, '
      f'got {len(backups)} from tmp_path contents: '
      f'{sorted(p.name for p in tmp_path.iterdir())}'
    )
    backup = backups[0]
    # Microsecond suffix must be present (B-2 hardening; not the bare-second format)
    assert '_' in backup.name.split('.')[-1], (
      f'B-2: microsecond suffix (underscore + microseconds) must appear in '
      f'backup filename {backup.name!r}'
    )
    # Backup contains the original garbage bytes (proves the rename, not a copy)
    assert backup.read_bytes() == b'\x00\xff\x00not json'

    # STATE-07: returned state is a fresh reset (D-05: no silent clobber of valid state)
    assert state['account'] == INITIAL_ACCOUNT
    assert state['positions'] == {'SPI200': None, 'AUDUSD': None}
    assert state['schema_version'] == STATE_SCHEMA_VERSION

    # D-07: warning appended with source='state_manager'
    assert len(state['warnings']) == 1, 'D-07: corruption-recovery warning must be appended'
    warning = state['warnings'][0]
    assert warning['source'] == 'state_manager'
    assert backup.name in warning['message'], (
      'D-07: warning message must reference the backup filename for forensics'
    )

    # The fresh state was persisted (so next run reads clean state.json, not garbage)
    assert path.exists(), 'load_state must rewrite a fresh state.json after recovery'
    on_disk = json.loads(path.read_text())
    assert on_disk == state, 'on-disk state must equal the returned state after recovery'

  def test_corruption_recovery_does_not_catch_non_json_value_error(
      self, tmp_path, monkeypatch) -> None:
    '''Pitfall 4 / D-05: load_state must catch ONLY JSONDecodeError, not bare ValueError.

    If _migrate raises a non-JSON ValueError (e.g., schema mismatch), it must
    propagate -- catching ValueError broadly would mask non-corruption bugs as
    spurious corruption events.
    '''
    path = tmp_path / 'state.json'
    # Write a syntactically VALID JSON state (so json.loads succeeds)
    valid_state = reset_state()
    path.write_text(json.dumps(valid_state, indent=2))

    # Monkeypatch _migrate to raise a non-JSON ValueError
    import state_manager
    def bad_migrate(s):
      raise ValueError('schema mismatch — not corruption')
    monkeypatch.setattr(state_manager, '_migrate', bad_migrate)

    # The ValueError must propagate, NOT be caught and trigger spurious backup
    with pytest.raises(ValueError, match='schema mismatch'):
      load_state(path=path)

    # No backup file was created (corruption recovery did NOT fire)
    backups = list(tmp_path.glob('state.json.corrupt.*'))
    assert backups == [], (
      f'Pitfall 4: non-JSON ValueError must NOT trigger corruption backup; '
      f'found spurious backup(s): {backups}'
    )

  def test_corrupt_state_returns_new_state_with_corruption_warning(self, tmp_path) -> None:
    '''D-07 + A1: warning has AWST date + state_manager source + descriptive message.'''
    path = tmp_path / 'state.json'
    path.write_bytes(b'definitely not json {')
    # 2026-04-21 09:30 UTC = 2026-04-21 17:30 AWST (same calendar date)
    fixed_now = datetime(2026, 4, 21, 9, 30, 45, 0, tzinfo=UTC)

    state = load_state(path=path, now=fixed_now)

    warning = state['warnings'][0]
    assert warning['date'] == '2026-04-21', 'A1: warning date is AWST YYYY-MM-DD'
    assert warning['source'] == 'state_manager'
    assert warning['message'].startswith('recovered from corruption'), warning['message']

  def test_load_state_valid_json_missing_keys_raises_value_error(self, tmp_path) -> None:
    '''D-18 (reviews-revision pass): valid JSON missing required top-level keys
    raises ValueError; does NOT trigger corruption backup (D-05 narrow catch
    preserved — _validate_loaded_state runs OUTSIDE the JSONDecodeError except
    block so its ValueError propagates).

    Reason: a file like {"schema_version": 1} parses fine, will migrate (no-op),
    and downstream code crashes with KeyError on state['account']. D-18 makes
    this surface as a specific ValueError at the load boundary so the operator
    sees a real error rather than a confusing downstream crash.
    '''
    path = tmp_path / 'state.json'
    # Valid JSON but MISSING 'account' (and 'positions', for stronger signal)
    bare_state = {
      'schema_version': STATE_SCHEMA_VERSION,
      'last_run': None,
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [],
      'equity_history': [],
      'warnings': [],
      # 'account' deliberately missing
      # 'positions' deliberately missing
    }
    path.write_text(json.dumps(bare_state, indent=2))

    # D-18: validator raises ValueError naming the missing keys
    with pytest.raises(ValueError, match='account'):
      load_state(path=path)

    # D-05 NARROWNESS PRESERVED: this was NOT corruption, so no backup created
    backups = list(tmp_path.glob('state.json.corrupt.*'))
    assert backups == [], (
      f'D-18 + D-05: valid-JSON-missing-keys must raise ValueError WITHOUT '
      f'triggering corruption backup; found spurious backup(s): {backups}. '
      f'D-18 validator must run OUTSIDE the JSONDecodeError except block.'
    )

  def test_backup_uses_path_derived_name_not_hardcoded(self, tmp_path) -> None:
    '''B-1 (reviews-revision pass): _backup_corrupt derives backup filename from
    path.name, not the hardcoded literal "state.json".

    For the canonical path (path.name == 'state.json') the result is identical
    to the original behavior. For non-default paths (tests, future reuse), the
    backup correctly mirrors the source filename.
    '''
    path = tmp_path / 'custom-state.json'
    path.write_bytes(b'\x00\xff\x00not json')
    fixed_now = datetime(2026, 4, 21, 9, 30, 45, 654321, tzinfo=UTC)

    load_state(path=path, now=fixed_now)

    # B-1: backup name derives from path.name, NOT hardcoded 'state.json'
    backups = list(tmp_path.glob('custom-state.json.corrupt.*'))
    assert len(backups) == 1, (
      f'B-1: expected 1 backup with name derived from custom-state.json; '
      f'got {len(backups)}. tmp_path contents: '
      f'{sorted(p.name for p in tmp_path.iterdir())}'
    )
    # Hardcoded 'state.json.corrupt.*' must NOT exist (would prove the bug)
    wrong_backups = list(tmp_path.glob('state.json.corrupt.*'))
    assert wrong_backups == [], (
      f'B-1: backup name must be derived from path.name (custom-state.json), '
      f'NOT hardcoded as state.json. Found wrong backup(s): {wrong_backups}'
    )
    # Backup is in the same directory as the source path
    assert backups[0].parent == tmp_path

class TestRecordTrade:
  '''STATE-05 / D-13..D-16 / D-19 / D-20: validation, closing-half cost,
  account mutation, position close, no-mutation contract.

  All arithmetic verified from first principles (no oracle files needed).
  CRITICAL: gross_pnl is RAW price-delta P&L per D-14, NOT realised_pnl.
  '''

  def _make_open_position(self) -> dict:
    '''Helper: return a Position-shaped dict for an open SPI200 LONG.'''
    return {
      'direction': 'LONG', 'entry_price': 7000.0, 'entry_date': '2026-01-02',
      'n_contracts': 2, 'pyramid_level': 0, 'peak_price': 7100.0,
      'trough_price': None, 'atr_entry': 53.0,
    }

  def test_record_trade_adjusts_account_by_net_pnl(self) -> None:
    '''D-14: closing_cost_half = 6.0 * 2 / 2 = 6.0; net_pnl = 1000.0 - 6.0 = 994.0.

    Arithmetic from first principles:
      cost_aud=6.0, n_contracts=2, gross_pnl=1000.0
      closing_cost_half = 6.0 * 2 / 2 = 6.0
      net_pnl = 1000.0 - 6.0 = 994.0
      account = 100_000.0 + 994.0 = 100_994.0
    '''
    state = reset_state()
    state['positions']['SPI200'] = self._make_open_position()
    trade = _make_trade(gross_pnl=1000.0, n_contracts=2, cost_aud=6.0)
    result = record_trade(state, trade)

    assert result['account'] == 100_994.0, (
      f'D-14: expected 100_994.0, got {result["account"]}'
    )

  def test_record_trade_appends_to_trade_log_with_net_pnl(self) -> None:
    '''STATE-05 / D-13 / D-20: trade-log entry has computed net_pnl;
    original trade dict (caller's input) is NOT mutated.
    '''
    state = reset_state()
    state['positions']['SPI200'] = self._make_open_position()
    trade = _make_trade(gross_pnl=1000.0, n_contracts=2, cost_aud=6.0)
    result = record_trade(state, trade)

    assert len(result['trade_log']) == 1
    logged = result['trade_log'][0]
    assert logged['net_pnl'] == 994.0, 'D-14: net_pnl in trade_log entry'
    assert logged['gross_pnl'] == 1000.0, 'original gross_pnl preserved in entry'
    assert logged['instrument'] == 'SPI200'
    assert logged['direction'] == 'LONG'

  def test_record_trade_sets_position_to_none(self) -> None:
    '''D-01 / D-13: positions[instrument] is None after record_trade (atomic close).'''
    state = reset_state()
    state['positions']['SPI200'] = self._make_open_position()
    trade = _make_trade()
    result = record_trade(state, trade)
    assert result['positions']['SPI200'] is None, (
      'D-01/D-13: record_trade must set positions[instrument] = None on close'
    )
    # AUDUSD untouched
    assert result['positions']['AUDUSD'] is None

  def test_record_trade_raises_on_missing_field(self) -> None:
    '''D-15: ValueError on missing required field, naming the offending key.'''
    state = reset_state()
    state['positions']['SPI200'] = self._make_open_position()
    trade = _make_trade()
    del trade['gross_pnl']
    with pytest.raises(ValueError, match='gross_pnl'):
      record_trade(state, trade)

  def test_record_trade_raises_on_invalid_instrument(self) -> None:
    '''D-15: ValueError on instrument not in {SPI200, AUDUSD}.'''
    state = reset_state()
    trade = _make_trade(instrument='NASDAQ')
    with pytest.raises(ValueError, match='instrument'):
      record_trade(state, trade)

  def test_record_trade_raises_on_invalid_direction(self) -> None:
    '''D-15: ValueError on direction not in {LONG, SHORT}.'''
    state = reset_state()
    trade = _make_trade(direction='HOLD')
    with pytest.raises(ValueError, match='direction'):
      record_trade(state, trade)

  def test_record_trade_raises_on_zero_or_negative_contracts(self) -> None:
    '''D-15: n_contracts must be int > 0.'''
    state = reset_state()
    # Zero contracts
    with pytest.raises(ValueError, match='n_contracts'):
      record_trade(state, _make_trade(n_contracts=0))
    # Negative contracts
    with pytest.raises(ValueError, match='n_contracts'):
      record_trade(state, _make_trade(n_contracts=-1))
    # Float contracts (not int)
    with pytest.raises(ValueError, match='n_contracts'):
      record_trade(state, _make_trade(n_contracts=1.5))

  def test_record_trade_raises_on_non_string_entry_date(self) -> None:
    '''D-19 (reviews-revision pass): entry_date must be non-empty str.'''
    state = reset_state()
    trade = _make_trade()
    trade['entry_date'] = 20260102  # int instead of str
    with pytest.raises(ValueError, match='entry_date'):
      record_trade(state, trade)

  def test_record_trade_raises_on_empty_string_exit_reason(self) -> None:
    '''D-19 (reviews-revision pass): exit_reason must be NON-EMPTY str.'''
    state = reset_state()
    trade = _make_trade()
    trade['exit_reason'] = ''
    with pytest.raises(ValueError, match='exit_reason'):
      record_trade(state, trade)

  def test_record_trade_raises_on_bool_for_numeric_field(self) -> None:
    '''D-19 (reviews-revision pass): numeric fields must reject bool.

    Python quirk: isinstance(True, int) is True. Without the explicit bool
    rejection, True would pass the (int|float) type check and silently
    corrupt arithmetic (gross_pnl=True would compute net_pnl = True - 6.0 = -5).
    '''
    state = reset_state()
    trade = _make_trade()
    trade['gross_pnl'] = True
    with pytest.raises(ValueError, match='gross_pnl'):
      record_trade(state, trade)

  def test_record_trade_raises_on_nan_gross_pnl(self) -> None:
    '''D-19 (reviews-revision pass): NaN numeric fields raise immediately
    rather than waiting for save_state's allow_nan=False catch later.
    '''
    state = reset_state()
    trade = _make_trade()
    trade['gross_pnl'] = float('nan')
    with pytest.raises(ValueError, match='gross_pnl'):
      record_trade(state, trade)

  def test_record_trade_raises_on_inf_cost_aud(self) -> None:
    '''D-19 (reviews-revision pass): infinite numeric fields raise.'''
    state = reset_state()
    trade = _make_trade()
    trade['cost_aud'] = float('inf')
    with pytest.raises(ValueError, match='cost_aud'):
      record_trade(state, trade)

  def test_record_trade_raises_on_string_entry_price(self) -> None:
    '''D-19 (reviews-revision pass): numeric fields reject str values.'''
    state = reset_state()
    trade = _make_trade()
    trade['entry_price'] = '7000.0'  # str instead of numeric
    with pytest.raises(ValueError, match='entry_price'):
      record_trade(state, trade)

  def test_record_trade_does_not_mutate_caller_trade_dict(self) -> None:
    """D-20 (reviews-revision pass): record_trade must NOT mutate the
    caller's trade dict. The trade_log entry is built via dict(trade,
    net_pnl=net_pnl) — a shallow copy with net_pnl added — so the
    caller's input dict is preserved verbatim. Phase 4 can safely reuse
    the trade dict afterwards.
    """
    state = reset_state()
    state['positions']['SPI200'] = self._make_open_position()
    trade = _make_trade(gross_pnl=1000.0, n_contracts=2, cost_aud=6.0)
    original_keys = set(trade.keys())
    original_gross_pnl = trade['gross_pnl']

    result = record_trade(state, trade)

    # D-20: caller's trade dict is unchanged
    assert 'net_pnl' not in trade, (
      "D-20: record_trade must NOT add net_pnl to caller's trade dict; "
      f'trade now has keys: {sorted(trade.keys())}'
    )
    assert set(trade.keys()) == original_keys, (
      f'D-20: trade dict keys must be unchanged; '
      f'before={sorted(original_keys)}, after={sorted(trade.keys())}'
    )
    assert trade['gross_pnl'] == original_gross_pnl, (
      'D-20: trade dict values must be unchanged'
    )

    # But the trade_log entry DOES carry net_pnl (it's a separate copy)
    assert result['trade_log'][0]['net_pnl'] == 994.0, (
      'D-20: trade_log entry must carry net_pnl (it is a copy of trade '
      'with net_pnl added)'
    )
    assert result['trade_log'][0] is not trade, (
      "D-20: trade_log entry must be a separate dict object, not the "
      "caller's trade dict by reference"
    )

  def test_record_trade_phase_4_boundary_gross_pnl_not_realised_pnl(self) -> None:
    '''CRITICAL Phase 4 boundary AC (RESEARCH §Pitfall 3 / Open Question 1).

    record_trade expects trade['gross_pnl'] = RAW price-delta P&L:
      (exit_price - entry_price) * n_contracts * multiplier  (LONG)

    Phase 2's ClosedTrade.realised_pnl is gross MINUS closing-half cost
    (Phase 2 _close_position already applied that deduction).

    If Phase 4 incorrectly passes ClosedTrade.realised_pnl as gross_pnl,
    record_trade will deduct the closing-half cost AGAIN, double-counting it.

    This test fixes the contract by exercising both paths with concrete
    numbers, so a future Phase 4 PR that misuses the boundary breaks this
    test loudly.

    Concrete example (SPI LONG, 2 contracts, $5/pt mult, $6 RT cost):
      entry_price = 7000, exit_price = 7100, n_contracts = 2, multiplier = 5.0
      RAW gross_pnl = (7100 - 7000) * 2 * 5.0 = 1000.0
      closing_cost_half = 6.0 * 2 / 2 = 6.0
      CORRECT net_pnl = 1000.0 - 6.0 = 994.0
      account = 100_000.0 + 994.0 = 100_994.0

      BUG path (if Phase 4 passed realised_pnl as gross_pnl):
        ClosedTrade.realised_pnl = RAW - closing_cost_half = 1000.0 - 6.0 = 994.0
        record_trade would compute: net_pnl = 994.0 - 6.0 = 988.0  (WRONG: $6 short)
        account would become 100_988.0 instead of 100_994.0

    Phase 4 must compute gross_pnl explicitly:
      gross_pnl = (exit_price - entry_price) * n_contracts * multiplier  for LONG
      gross_pnl = (entry_price - exit_price) * n_contracts * multiplier  for SHORT
    and pass THAT to record_trade — NOT ClosedTrade.realised_pnl.
    '''
    # CORRECT path: gross_pnl is RAW
    state = reset_state()
    state['positions']['SPI200'] = self._make_open_position()
    correct_trade = _make_trade(
      entry_price=7000.0, exit_price=7100.0, n_contracts=2,
      gross_pnl=1000.0,  # RAW: (7100 - 7000) * 2 * 5.0 = 1000.0
      cost_aud=6.0, multiplier=5.0,
    )
    result = record_trade(state, correct_trade)
    assert result['account'] == 100_994.0, (
      'CORRECT: gross_pnl=1000.0 (raw) -> net_pnl=994.0 -> account=100_994.0'
    )
    assert result['trade_log'][0]['net_pnl'] == 994.0

    # BUG path simulation: if Phase 4 passes realised_pnl (already net of close cost)
    # as gross_pnl, record_trade double-deducts and account is short by 6.0.
    # This is the bug Phase 4 MUST avoid.
    state2 = reset_state()
    state2['positions']['SPI200'] = self._make_open_position()
    # Simulate what Phase 2 ClosedTrade.realised_pnl would be:
    # phase2_realised_pnl = RAW - closing_cost_half = 1000.0 - 6.0 = 994.0
    phase2_realised_pnl = 994.0
    bug_trade = _make_trade(
      entry_price=7000.0, exit_price=7100.0, n_contracts=2,
      gross_pnl=phase2_realised_pnl,  # WRONG: passing realised_pnl as gross_pnl
      cost_aud=6.0, multiplier=5.0,
    )
    bug_result = record_trade(state2, bug_trade)
    # The bug: account is understated by exactly closing_cost_half = 6.0
    assert bug_result['account'] == 100_988.0, (
      'BUG: passing realised_pnl as gross_pnl double-deducts close cost; '
      'account becomes 100_988.0 instead of 100_994.0 (short by 6.0). '
      'Phase 4 MUST compute gross_pnl as RAW price-delta and pass THAT.'
    )
    # The bug delta is exactly closing_cost_half — proves the cause
    assert (
      (result['account'] - bug_result['account']) ==
      (correct_trade['cost_aud'] * correct_trade['n_contracts'] / 2)
    ), 'bug magnitude must equal closing_cost_half'

class TestEquityHistory:
  '''STATE-06 / D-04 / B-4: update_equity_history appends {date, equity}
  after boundary validation (date shape + equity finiteness).
  '''

  def test_update_equity_history_appends_entry(self) -> None:
    '''STATE-06: append {date, equity} entry to equity_history.'''
    state = reset_state()
    result = update_equity_history(state, '2026-04-21', 99_500.0)
    assert len(result['equity_history']) == 1
    entry = result['equity_history'][0]
    assert entry == {'date': '2026-04-21', 'equity': 99_500.0}, (
      f'STATE-06: entry shape must be {{date, equity}}; got {entry}'
    )

  def test_update_equity_history_appends_multiple_entries_in_order(self) -> None:
    '''Multiple appends preserve chronological order.'''
    state = reset_state()
    state = update_equity_history(state, '2026-04-19', 99_500.0)
    state = update_equity_history(state, '2026-04-20', 99_750.0)
    state = update_equity_history(state, '2026-04-21', 99_000.5)
    assert len(state['equity_history']) == 3
    dates = [e['date'] for e in state['equity_history']]
    equities = [e['equity'] for e in state['equity_history']]
    assert dates == ['2026-04-19', '2026-04-20', '2026-04-21']
    assert equities == [99_500.0, 99_750.0, 99_000.5]

  def test_update_equity_history_returns_mutated_state(self) -> None:
    '''Pattern: all mutation functions return the mutated state for chaining.'''
    state = reset_state()
    result = update_equity_history(state, '2026-04-21', 100_000.0)
    assert result is state, (
      'update_equity_history must return the same state dict reference'
    )

  def test_update_equity_history_raises_on_non_string_date(self) -> None:
    '''B-4 (reviews-revision pass): date must be str (not int / datetime / etc).'''
    state = reset_state()
    with pytest.raises(ValueError, match='date'):
      update_equity_history(state, 20260421, 99_500.0)  # int instead of str

  def test_update_equity_history_raises_on_short_date_string(self) -> None:
    '''B-4 (reviews-revision pass): date must be str of length 10 (ISO YYYY-MM-DD shape).'''
    state = reset_state()
    with pytest.raises(ValueError, match='date'):
      update_equity_history(state, '2026-04', 99_500.0)  # len 7, not 10

  def test_update_equity_history_raises_on_non_finite_equity(self) -> None:
    '''B-4 (reviews-revision pass): equity must be finite numeric (rejects NaN, inf, bool).'''
    state = reset_state()
    with pytest.raises(ValueError, match='equity'):
      update_equity_history(state, '2026-04-21', float('nan'))
    with pytest.raises(ValueError, match='equity'):
      update_equity_history(state, '2026-04-21', float('inf'))
    with pytest.raises(ValueError, match='equity'):
      update_equity_history(state, '2026-04-21', True)  # bool

class TestReset:
  '''STATE-07 / D-01 / D-03: reset_state shape — $100k account, None positions,
  FLAT signals, empty collections.

  Wave 2 fills this in.
  '''

  def test_reset_state_has_all_10_top_level_keys(self) -> None:
    '''STATE-01 (extended Phase 8 v2): reset_state returns dict with exactly
    10 top-level keys — 8 original + 2 Phase 8 additions (initial_account,
    contracts) required by _validate_loaded_state under schema v2.'''
    state = reset_state()
    expected_keys = {
      'schema_version', 'account', 'last_run', 'positions',
      'signals', 'trade_log', 'equity_history', 'warnings',
      # Phase 8 (v2 schema): CONF-01 + CONF-02 top-level keys
      'initial_account', 'contracts',
    }
    assert set(state.keys()) == expected_keys, (
      f'STATE-01 (v2): reset_state keys mismatch. Expected {sorted(expected_keys)}, '
      f'got {sorted(state.keys())}'
    )

  def test_reset_state_canonical_default_values(self) -> None:
    '''STATE-07 / D-01 / D-03: every default value matches CONTEXT.md.'''
    state = reset_state()
    assert state['schema_version'] == STATE_SCHEMA_VERSION
    assert state['account'] == INITIAL_ACCOUNT
    assert state['last_run'] is None
    assert state['positions'] == {'SPI200': None, 'AUDUSD': None}, 'D-01: None when flat'
    assert state['signals'] == {'SPI200': 0, 'AUDUSD': 0}, 'D-03: FLAT=0 init'
    assert state['trade_log'] == []
    assert state['equity_history'] == []
    assert state['warnings'] == []

  def test_reset_state_returns_independent_dicts(self) -> None:
    '''Idempotence: mutating one returned state must not affect a future reset.'''
    first = reset_state()
    first['trade_log'].append({'instrument': 'SPI200'})
    first['warnings'].append({'date': '2026-04-21', 'source': 'x', 'message': 'y'})
    second = reset_state()
    assert second['trade_log'] == [], (
      'reset_state must return a NEW dict each call, not share mutable refs'
    )
    assert second['warnings'] == []


class TestResetState:
  '''Phase 10 BUG-01 D-02 / D-03: reset_state signature accepts custom
  initial_account; default preserves backward compat.
  '''

  def test_reset_state_accepts_custom_initial_account(self) -> None:
    '''D-02: reset_state(initial_account=50000) sets BOTH account and
    initial_account to 50000.0 (invariant: they must be equal).'''
    state = reset_state(initial_account=50000)
    assert state['account'] == 50000.0
    assert state['initial_account'] == 50000.0
    assert state['account'] == state['initial_account'], (
      'BUG-01 invariant: account and initial_account must be equal '
      'immediately after reset'
    )

  def test_reset_state_custom_initial_account_edge_one_dollar(self) -> None:
    '''D-02: edge — tiny initial_account still pairs account == initial_account.'''
    state = reset_state(initial_account=1.0)
    assert state['account'] == 1.0
    assert state['initial_account'] == 1.0

  def test_reset_state_default_preserves_backward_compat(self) -> None:
    '''D-02: reset_state() with no arg still returns INITIAL_ACCOUNT
    for both fields. Phase 3 callers + corrupt-recovery path stay green.'''
    state = reset_state()
    assert state['account'] == INITIAL_ACCOUNT
    assert state['initial_account'] == INITIAL_ACCOUNT
    assert state['account'] == state['initial_account']

  def test_reset_state_custom_initial_account_does_not_affect_other_fields(self) -> None:
    '''D-02: other canonical fields unchanged when custom initial_account passed.'''
    state = reset_state(initial_account=50000)
    assert state['positions'] == {'SPI200': None, 'AUDUSD': None}
    assert state['signals'] == {'SPI200': 0, 'AUDUSD': 0}
    assert state['trade_log'] == []
    assert state['equity_history'] == []
    assert state['warnings'] == []
    assert state['last_run'] is None


class TestWarnings:
  '''D-09 / D-10 / D-11 / B-5: warning shape, AWST date, FIFO bound to MAX_WARNINGS.

  Wave 2 fills this in.
  '''

  def test_append_warning_basic_shape(self) -> None:
    '''D-09: warning entry has exactly {date, source, message} keys.'''
    state = reset_state()
    fixed_now = datetime(2026, 4, 21, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'sizing_engine', 'size=0: vol_scale clip', now=fixed_now)
    assert len(state['warnings']) == 1
    warning = state['warnings'][0]
    assert set(warning.keys()) == {'date', 'source', 'message'}, (
      f'D-09: warning shape must be exactly date+source+message; got {sorted(warning.keys())}'
    )
    assert warning['date'] == '2026-04-21'
    assert warning['source'] == 'sizing_engine'
    assert warning['message'] == 'size=0: vol_scale clip'

  def test_append_warning_date_uses_awst(self) -> None:
    '''D-09 + A1: warning.date is AWST (Australia/Perth), ISO YYYY-MM-DD.

    Inject a UTC datetime that corresponds to morning UTC = same AWST date.
    2026-04-21 09:30 UTC = 2026-04-21 17:30 AWST (same date).
    '''
    state = reset_state()
    now_utc = datetime(2026, 4, 21, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'state_manager', 'test msg', now=now_utc)
    assert state['warnings'][0]['date'] == '2026-04-21'

  def test_append_warning_fifo_trims_oldest_entries(self) -> None:
    '''D-11: 105 appends -> len(warnings) == MAX_WARNINGS (=100); oldest 5 dropped.'''
    state = reset_state()
    fixed_now = datetime(2026, 4, 21, 9, 0, 0, tzinfo=UTC)
    for i in range(105):
      state = append_warning(state, 'test', f'msg {i}', now=fixed_now)
    assert len(state['warnings']) == MAX_WARNINGS, (
      f'D-11: bound to MAX_WARNINGS={MAX_WARNINGS}; got {len(state["warnings"])}'
    )
    # Oldest 5 (msg 0..4) must be gone; msg 5 is the new first entry
    assert state['warnings'][0]['message'] == 'msg 5', (
      'D-11: FIFO must drop oldest entries first'
    )
    # Most recent is msg 104
    assert state['warnings'][-1]['message'] == 'msg 104'

  def test_append_warning_returns_mutated_state(self) -> None:
    '''Pattern: all mutation functions return the mutated state for chaining.'''
    state = reset_state()
    fixed_now = datetime(2026, 4, 21, 9, 0, 0, tzinfo=UTC)
    result = append_warning(state, 'test', 'msg', now=fixed_now)
    assert result is state, 'append_warning must return the same state dict reference'

class TestSchemaVersion:
  '''STATE-04: MIGRATIONS dict walk-forward; no-op at v1; handles missing key.

  Wave 1 fills this in.
  '''

  def test_migrations_dict_has_v1_no_op(self) -> None:
    '''STATE-04: MIGRATIONS[1] is the identity (no-op) per CONTEXT.md.'''
    sample = {'x': 1, 'y': 'two'}
    assert MIGRATIONS[1](sample) == sample, 'v1 migration must be identity (no-op hook)'

  def test_current_schema_no_op_migration(self, tmp_path) -> None:
    '''STATE-04 (extended Phase 8): a state at STATE_SCHEMA_VERSION on disk
    loads with schema_version unchanged and all fields preserved. Both the
    v1 identity hook AND the v2 backfill are no-ops when state is already
    at the current version with all required keys present.'''
    path = tmp_path / 'state.json'
    state = {
      'schema_version': STATE_SCHEMA_VERSION,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      # Phase 8 (v2 schema): CONF-01 + CONF-02 required keys. Under v2,
      # s.get(..., default) in MIGRATIONS[2] is idempotent — preserves
      # existing values without overwriting.
      'initial_account': INITIAL_ACCOUNT,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
    }
    save_state(state, path=path)
    loaded = load_state(path=path)
    assert loaded['schema_version'] == STATE_SCHEMA_VERSION
    # Phase 8: strip runtime-only _resolved_contracts before equality
    loaded_persisted = {k: v for k, v in loaded.items() if not k.startswith('_')}
    assert loaded_persisted == state, 'no-op migration must not mutate any field'

  def test_load_state_without_schema_version_key_migrates_to_current(self, tmp_path) -> None:
    '''Pitfall 5: state without schema_version key defaults to 0, walks forward to current.'''
    path = tmp_path / 'state.json'
    # Write a state dict to disk WITHOUT schema_version
    bare_state = {
      'account': INITIAL_ACCOUNT, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    path.write_text(json.dumps(bare_state, indent=2))
    loaded = load_state(path=path)
    assert loaded['schema_version'] == STATE_SCHEMA_VERSION, (
      'missing schema_version must default to 0 and walk to current'
    )

# =========================================================================
# Phase 8 test classes — v2 migration, underscore filter, tier resolve, clear_warnings
# =========================================================================

class TestMigrateV2Backfill:
  '''Phase 8 D-15: _migrate fills initial_account + contracts silently on
  pre-Phase-8 state.json without appending a warning. Idempotent for states
  that already have the keys set (operator's choice preserved).'''

  def test_v0_state_gets_initial_account_and_contracts_defaults(self) -> None:
    '''D-15: state without schema_version (→ v0) + no initial_account + no
    contracts → _migrate adds both with defaults.'''
    state = {
      # no schema_version key → defaults to 0 in _migrate
      'account': INITIAL_ACCOUNT, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    migrated = _migrate(state)
    assert migrated['initial_account'] == INITIAL_ACCOUNT, (
      f'D-15: v0 → v2 must add initial_account default; got {migrated.get("initial_account")!r}'
    )
    assert migrated['contracts'] == {
      'SPI200': _DEFAULT_SPI_LABEL, 'AUDUSD': _DEFAULT_AUDUSD_LABEL,
    }, f'D-15: v0 → v2 must add contracts defaults; got {migrated.get("contracts")!r}'

  def test_v1_state_gets_only_phase8_keys_backfilled(self) -> None:
    '''D-15: state at schema_version=1 with other fields intact → _migrate
    adds initial_account + contracts only; does NOT overwrite existing keys.'''
    state = {
      'schema_version': 1,
      'account': 85432.10, 'last_run': '2026-03-15',
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 1, 'AUDUSD': -1},
      'trade_log': [{'instrument': 'SPI200', 'net_pnl': 250.0}],
      'equity_history': [{'date': '2026-03-14', 'equity': 85000.0}],
      'warnings': [],
    }
    migrated = _migrate(state)
    # Phase 8 keys backfilled
    assert 'initial_account' in migrated
    assert 'contracts' in migrated
    # Existing keys untouched
    assert migrated['account'] == 85432.10
    assert migrated['last_run'] == '2026-03-15'
    assert migrated['signals'] == {'SPI200': 1, 'AUDUSD': -1}
    assert migrated['trade_log'] == [{'instrument': 'SPI200', 'net_pnl': 250.0}]
    assert migrated['equity_history'] == [{'date': '2026-03-14', 'equity': 85000.0}]

  def test_v2_state_has_existing_initial_account_preserved(self) -> None:
    '''D-15 idempotence: the s.get(..., default) pattern preserves existing
    values. A state already carrying initial_account=50000.0 keeps it —
    the lambda never overwrites operator choice.'''
    state = {
      'schema_version': 1,  # force re-run of MIGRATIONS[2]
      'account': 50000.0, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      # Operator's CONF-01 choice:
      'initial_account': 50000.0,
      'contracts': {'SPI200': 'spi-standard', 'AUDUSD': 'audusd-mini'},
    }
    migrated = _migrate(state)
    assert migrated['initial_account'] == 50000.0, (
      'D-15: existing initial_account must be preserved (idempotent)'
    )
    assert migrated['contracts'] == {
      'SPI200': 'spi-standard', 'AUDUSD': 'audusd-mini',
    }, 'D-15: existing contracts must be preserved (idempotent)'

  def test_migrate_v2_appends_no_warning(self) -> None:
    '''D-15: _migrate on v1 state MUST NOT append a warning — silent
    migration. Backfill is transparent to the operator.'''
    state = {
      'schema_version': 1,
      'account': INITIAL_ACCOUNT, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    warnings_before = list(state['warnings'])  # copy
    migrated = _migrate(state)
    assert migrated['warnings'] == warnings_before, (
      f'D-15: _migrate must NOT append a warning; '
      f'before={warnings_before!r} after={migrated["warnings"]!r}'
    )

  def test_migrate_walks_schema_version_to_current(self) -> None:
    '''STATE-04 (Phase 22 extension): after _migrate, schema_version equals
    STATE_SCHEMA_VERSION (now 4 per Phase 22 D-04 — was 3 under Phase 14 D-09).'''
    state = {
      # no schema_version → defaults to 0
      'account': INITIAL_ACCOUNT, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    migrated = _migrate(state)
    assert migrated['schema_version'] == STATE_SCHEMA_VERSION
    assert STATE_SCHEMA_VERSION >= 4, (
      'STATE_SCHEMA_VERSION was 4 at Phase 22, bumped to 5 at Phase 17 D-08; '
      'must be >= 4'
    )


class TestSaveStateExcludesUnderscoreKeys:
  '''Phase 8 D-14: save_state filters out any key starting with underscore.
  The convention is runtime-only — these keys never cross the disk boundary.
  Rule applies to _resolved_contracts AND Plan 03's future _stale_info.'''

  def test_resolved_contracts_not_persisted(self, tmp_path) -> None:
    '''D-14: _resolved_contracts is the canonical runtime-only key; must NOT
    appear in the on-disk state.json.'''
    path = tmp_path / 'state.json'
    state = reset_state()
    state['_resolved_contracts'] = {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
    }
    save_state(state, path=path)
    on_disk = json.loads(path.read_text())
    assert '_resolved_contracts' not in on_disk, (
      f'D-14: _resolved_contracts must NOT appear on disk; '
      f'disk keys: {sorted(on_disk.keys())}'
    )

  def test_arbitrary_underscore_key_not_persisted(self, tmp_path) -> None:
    '''D-14 general rule: ANY key with underscore prefix is stripped. This
    test guards against regressions where the filter is narrowed to only
    _resolved_contracts — the convention is the whole namespace.'''
    path = tmp_path / 'state.json'
    state = reset_state()
    state['_arbitrary'] = 'runtime-only-secret'
    state['_another_transient'] = {'foo': 'bar'}
    save_state(state, path=path)
    on_disk = json.loads(path.read_text())
    assert '_arbitrary' not in on_disk
    assert '_another_transient' not in on_disk

  def test_stale_info_not_persisted(self, tmp_path) -> None:
    '''D-14 (Plan 03 regression guard): _stale_info is Plan 03's transient
    signal for the stale-state banner. Must NOT be persisted — the filter
    at the state_manager layer gives Plan 03 the invariant it needs
    without a separate opt-in.'''
    path = tmp_path / 'state.json'
    state = reset_state()
    state['_stale_info'] = {'days_stale': 3, 'last_run_date': '2026-04-20'}
    save_state(state, path=path)
    on_disk = json.loads(path.read_text())
    assert '_stale_info' not in on_disk, (
      f'D-14: _stale_info must NOT appear on disk (Plan 03 regression guard); '
      f'disk keys: {sorted(on_disk.keys())}'
    )

  def test_public_keys_all_persisted(self, tmp_path) -> None:
    '''D-14: filter is UNDERSCORE-ONLY. All 10 v2-required public keys
    (schema_version, account, last_run, positions, signals, trade_log,
    equity_history, warnings, initial_account, contracts) persist.'''
    path = tmp_path / 'state.json'
    state = reset_state()
    save_state(state, path=path)
    on_disk = json.loads(path.read_text())
    expected = {
      'schema_version', 'account', 'last_run', 'positions',
      'signals', 'trade_log', 'equity_history', 'warnings',
      'initial_account', 'contracts',
    }
    assert expected <= set(on_disk.keys()), (
      f'D-14: all 10 v2-required public keys must persist; '
      f'missing={sorted(expected - set(on_disk.keys()))}'
    )

  def test_save_does_not_mutate_in_memory_state(self, tmp_path) -> None:
    '''D-14: save_state builds a new persisted dict via the filter; the
    caller's in-memory state dict is untouched so _resolved_contracts
    remains available for the rest of the run.'''
    path = tmp_path / 'state.json'
    state = reset_state()
    state['_resolved_contracts'] = {
      'SPI200': {'multiplier': 5.0, 'cost_aud': 6.0},
      'AUDUSD': {'multiplier': 10000.0, 'cost_aud': 5.0},
    }
    save_state(state, path=path)
    # In-memory state STILL has _resolved_contracts after save
    assert '_resolved_contracts' in state, (
      'D-14: save_state must not mutate the caller\'s dict; '
      '_resolved_contracts must remain on the in-memory state.'
    )
    assert state['_resolved_contracts']['SPI200'] == {'multiplier': 5.0, 'cost_aud': 6.0}


class TestLoadStateResolvesContracts:
  '''Phase 8 D-14: load_state materialises _resolved_contracts from the
  tier labels in state['contracts'], looking up each label in the
  corresponding system_params.*_CONTRACTS dict. Unknown labels raise
  KeyError (operator surfaces it + runs --reset; hex rule preserved).'''

  def test_load_state_resolves_spi_mini(self, tmp_path) -> None:
    '''D-14: state with contracts = {SPI200: spi-mini, AUDUSD: audusd-standard}
    resolves to the SPI mini + AUDUSD standard tier values.'''
    path = tmp_path / 'state.json'
    state = reset_state()
    # Defaults are spi-mini + audusd-standard, so reset_state already matches
    save_state(state, path=path)
    loaded = load_state(path=path)
    assert loaded['_resolved_contracts']['SPI200'] == {
      'multiplier': 5.0, 'cost_aud': 6.0,
    }, f'D-14: expected spi-mini tier values; got {loaded["_resolved_contracts"]["SPI200"]}'
    assert loaded['_resolved_contracts']['AUDUSD'] == {
      'multiplier': 10000.0, 'cost_aud': 5.0,
    }, f'D-14: expected audusd-standard tier values; got {loaded["_resolved_contracts"]["AUDUSD"]}'

  def test_load_state_resolves_spi_standard_and_audusd_mini(self, tmp_path) -> None:
    '''D-14: a different tier combination (spi-standard + audusd-mini)
    resolves to the correct tier values from SPI_CONTRACTS / AUDUSD_CONTRACTS.'''
    path = tmp_path / 'state.json'
    state = reset_state()
    state['contracts'] = {'SPI200': 'spi-standard', 'AUDUSD': 'audusd-mini'}
    save_state(state, path=path)
    loaded = load_state(path=path)
    assert loaded['_resolved_contracts']['SPI200'] == {
      'multiplier': 25.0, 'cost_aud': 30.0,
    }
    assert loaded['_resolved_contracts']['AUDUSD'] == {
      'multiplier': 1000.0, 'cost_aud': 0.5,
    }

  def test_load_state_unknown_label_raises_key_error(self, tmp_path) -> None:
    '''D-14: an unknown label in state['contracts'] raises KeyError naming
    the offending label. Hex rule: caller surfaces and operator runs --reset.

    The state is written directly (bypassing save_state — which would
    happily persist the bogus label) so the schema is valid JSON with
    all required keys, but the label lookup fails on load.'''
    path = tmp_path / 'state.json'
    bogus_state = {
      'schema_version': STATE_SCHEMA_VERSION,
      'account': INITIAL_ACCOUNT, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': INITIAL_ACCOUNT,
      'contracts': {'SPI200': 'spi-made-up', 'AUDUSD': 'audusd-standard'},
    }
    path.write_text(json.dumps(bogus_state, indent=2))
    with pytest.raises(KeyError, match='spi-made-up'):
      load_state(path=path)

  def test_load_state_on_fresh_reset_resolves_defaults(self, tmp_path) -> None:
    '''D-14: reset_state emits default labels; after save + load, the
    materialised _resolved_contracts matches spi-mini / audusd-standard.'''
    path = tmp_path / 'state.json'
    state = reset_state()
    save_state(state, path=path)
    loaded = load_state(path=path)
    assert loaded['_resolved_contracts']['SPI200'] == SPI_CONTRACTS[_DEFAULT_SPI_LABEL]
    assert loaded['_resolved_contracts']['AUDUSD'] == AUDUSD_CONTRACTS[_DEFAULT_AUDUSD_LABEL]


class TestClearWarnings:
  '''Phase 8 D-02: clear_warnings empties state['warnings'] in place and
  returns the same dict. Preserves D-10 sole-writer invariant — state_manager
  is the ONLY module that mutates state['warnings'].'''

  def test_clear_warnings_empties_list(self) -> None:
    '''D-02: state with 3 warning entries → after clear_warnings, list is empty.'''
    state = reset_state()
    fixed_now = datetime(2026, 4, 22, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'sizing_engine', 'msg 1', now=fixed_now)
    state = append_warning(state, 'state_manager', 'msg 2', now=fixed_now)
    state = append_warning(state, 'notifier', 'msg 3', now=fixed_now)
    assert len(state['warnings']) == 3, 'precondition: 3 warnings appended'
    result = clear_warnings(state)
    assert result['warnings'] == [], (
      f'D-02: clear_warnings must empty state["warnings"]; got {result["warnings"]!r}'
    )

  def test_clear_warnings_preserves_other_keys(self) -> None:
    '''D-02: clear_warnings only touches state["warnings"]; all other
    top-level keys (account, positions, signals, trade_log, etc.) remain
    untouched.'''
    state = reset_state()
    fixed_now = datetime(2026, 4, 22, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'sizing_engine', 'msg 1', now=fixed_now)
    # Capture non-warning state snapshot
    snapshot = {k: v for k, v in state.items() if k != 'warnings'}
    clear_warnings(state)
    after_snapshot = {k: v for k, v in state.items() if k != 'warnings'}
    assert after_snapshot == snapshot, (
      'D-02: clear_warnings must NOT touch any key other than warnings'
    )

  def test_clear_warnings_in_place_mutation(self) -> None:
    '''D-02: clear_warnings returns the SAME dict reference (in-place
    mutation pattern — like append_warning, record_trade).'''
    state = reset_state()
    fixed_now = datetime(2026, 4, 22, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'sizing_engine', 'msg', now=fixed_now)
    result = clear_warnings(state)
    assert result is state, (
      'D-02: clear_warnings must return the same dict reference (in-place)'
    )

  def test_clear_warnings_on_empty_list_is_noop(self) -> None:
    '''D-02: calling clear_warnings on a state with no warnings is a no-op
    and does not raise.'''
    state = reset_state()
    assert state['warnings'] == [], 'precondition: fresh state has empty warnings'
    result = clear_warnings(state)
    assert result['warnings'] == []
    assert result is state


class TestClearWarningsBySource:
  '''Phase 15 D-02: clear_warnings_by_source filters state['warnings'] by
  `source` key, leaving non-matching warnings intact. Pure dict-op; sole
  writer to state['warnings']. Wave 0 skeleton — bodies populated in Plan 03.
  '''

  def test_removes_matching_source(self) -> None:
    from state_manager import (
      append_warning,
      clear_warnings_by_source,
      reset_state,
    )
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'drift', 'msg drift 1', now=fixed_now)
    state = append_warning(state, 'drift', 'msg drift 2', now=fixed_now)
    state = append_warning(state, 'sizing_engine', 'msg sizing', now=fixed_now)
    assert len(state['warnings']) == 3, 'precondition: 3 warnings appended'
    clear_warnings_by_source(state, 'drift')
    assert len(state['warnings']) == 1
    assert state['warnings'][0]['source'] == 'sizing_engine'
    assert state['warnings'][0]['message'] == 'msg sizing'

  def test_leaves_other_sources_intact(self) -> None:
    from state_manager import (
      append_warning,
      clear_warnings_by_source,
      reset_state,
    )
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'state_manager', 'corruption msg', now=fixed_now)
    state = append_warning(state, 'sizing_engine', 'sizing msg', now=fixed_now)
    state = append_warning(state, 'notifier', 'notif msg', now=fixed_now)
    clear_warnings_by_source(state, 'drift')  # no drift warnings exist
    assert len(state['warnings']) == 3
    sources = sorted(w['source'] for w in state['warnings'])
    assert sources == ['notifier', 'sizing_engine', 'state_manager']

  def test_idempotent_on_no_match(self) -> None:
    from state_manager import (
      append_warning,
      clear_warnings_by_source,
      reset_state,
    )
    state = reset_state()
    fixed_now = datetime(2026, 4, 26, 9, 30, 0, tzinfo=UTC)
    state = append_warning(state, 'sizing_engine', 'a', now=fixed_now)
    before = list(state['warnings'])
    clear_warnings_by_source(state, 'drift')
    clear_warnings_by_source(state, 'drift')  # second call, no change
    assert state['warnings'] == before

  def test_returns_same_state_reference(self) -> None:
    from state_manager import clear_warnings_by_source, reset_state
    state = reset_state()
    result = clear_warnings_by_source(state, 'drift')
    assert result is state, 'must return same dict for chaining (mirrors clear_warnings contract)'

  def test_handles_missing_warnings_key(self) -> None:
    from state_manager import clear_warnings_by_source
    state: dict = {}  # no 'warnings' key at all
    result = clear_warnings_by_source(state, 'drift')
    assert result is state
    assert result['warnings'] == []  # set to empty list after the call


# =========================================================================
# Phase 14 D-13 — fcntl exclusive lock around _atomic_write
# =========================================================================

class TestFcntlLock:
  '''Phase 14 D-13: cross-process state.json coordination via fcntl.LOCK_EX.

  Lock is on the destination state.json. Acquired in _atomic_write before
  tempfile->replace; released by explicit LOCK_UN + os.close. Blocking-
  indefinite per D-13.

  Cross-process correctness verified via multiprocessing.Process holder
  that opens state.json + flock(LOCK_EX) + sleeps 0.5s; main test calls
  save_state() and asserts elapsed >= 0.4s (proves contention) and < 1.5s
  (proves no zombie wait).
  '''

  @staticmethod
  def _hold_lock_for(path_str, hold_seconds, ready_event):
    import fcntl, os, time
    fd = os.open(path_str, os.O_RDWR | os.O_CREAT, 0o600)
    try:
      fcntl.flock(fd, fcntl.LOCK_EX)
      ready_event.set()
      time.sleep(hold_seconds)
    finally:
      fcntl.flock(fd, fcntl.LOCK_UN)
      os.close(fd)

  def test_save_state_blocks_when_external_lock_held(self, tmp_path) -> None:
    import multiprocessing as mp
    import time
    path = tmp_path / 'state.json'
    save_state(reset_state(), path=path)
    ctx = mp.get_context('spawn')
    ready = ctx.Event()
    proc = ctx.Process(target=self._hold_lock_for, args=(str(path), 0.5, ready))
    proc.start()
    try:
      assert ready.wait(timeout=2.0)
      state = reset_state()
      state['account'] = 12345.0
      start = time.perf_counter()
      save_state(state, path=path)
      elapsed = time.perf_counter() - start
    finally:
      proc.join(timeout=2.0)
      if proc.is_alive():
        proc.terminate()
        proc.join()
    assert elapsed >= 0.4, f'D-13: did not block; elapsed={elapsed:.3f}s'
    assert elapsed < 1.5, f'D-13: too slow after release; elapsed={elapsed:.3f}s'
    assert load_state(path=path)['account'] == 12345.0

  def test_save_state_releases_lock_after_successful_write(self, tmp_path) -> None:
    import fcntl
    import time
    path = tmp_path / 'state.json'
    start = time.perf_counter()
    save_state(reset_state(), path=path)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1
    fd = os.open(str(path), os.O_RDWR)
    try:
      fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
      fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
      os.close(fd)

  def test_save_state_releases_lock_after_failed_os_replace(self, tmp_path) -> None:
    import fcntl
    path = tmp_path / 'state.json'
    save_state(reset_state(), path=path)
    new_state = reset_state()
    new_state['account'] = 7777.0
    with patch('state_manager.os.replace', side_effect=OSError('disk full')):
      with pytest.raises(OSError, match='disk full'):
        save_state(new_state, path=path)
    fd = os.open(str(path), os.O_RDWR)
    try:
      fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
      fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
      os.close(fd)

  def test_two_sequential_save_state_calls_both_succeed(self, tmp_path) -> None:
    path = tmp_path / 'state.json'
    for i in range(2):
      state = reset_state()
      state['account'] = float(i)
      save_state(state, path=path)
    assert load_state(path=path)['account'] == 1.0


# =========================================================================
# Phase 14 D-13 + REVIEWS HIGH #1 — mutate_state full critical-section lock
# =========================================================================

class TestMutateState:
  '''Phase 14 D-13 + REVIEWS HIGH #1: mutate_state holds fcntl.LOCK_EX
  across the FULL load -> mutate -> save critical section.

  Without this helper, fcntl on save_state alone admits stale-read lost
  updates: two writers can both load the same pre-mutation snapshot, both
  acquire+release the save lock, second clobbers first. mutate_state
  closes that race.

  Tests cover:
    - happy-path: load -> mutate -> save round-trip
    - cross-process: two processes both call mutate_state with non-
      conflicting mutations; both mutations visible in final state
      (the previous fcntl-on-save-only design FAILED this test by losing
      one of the mutations)
    - mutator exception: lock released, state unchanged
    - reentrancy: save_state nested inside mutator on a DIFFERENT path
      succeeds (intra-process flock-on-different-fd-of-different-file
      is OK; flock-on-different-fd-of-SAME-file would deadlock and is
      structurally avoided by mutate_state's _save_state_unlocked path)
    - return value: mutate_state returns the post-save state
  '''

  def test_load_mutate_save_atomic(self, tmp_path) -> None:
    '''Happy path: mutator applied, state persisted.'''
    from state_manager import mutate_state
    path = tmp_path / 'state.json'
    save_state(reset_state(), path=path)

    def _bump(state):
      state['account'] = 99999.0

    result = mutate_state(_bump, path=path)
    assert result['account'] == 99999.0
    assert load_state(path=path)['account'] == 99999.0

  @staticmethod
  def _subprocess_mutate(path_str, key, value, ready_event, go_event):
    '''Subprocess body: signal ready, wait for go, then mutate_state.'''
    import sys
    import os as _os
    from pathlib import Path as _Path
    # Ensure project on sys.path (parent of tests/)
    proj = _os.path.dirname(_os.path.dirname(_os.path.abspath(path_str)))
    # The test's tmp_path is OUTSIDE the project tree on macOS;
    # locate the project root instead via the test's discoverable tree.
    # Walk up from cwd until we find state_manager.py.
    p = _os.getcwd()
    while p and not _os.path.exists(_os.path.join(p, 'state_manager.py')):
      parent = _os.path.dirname(p)
      if parent == p:
        break
      p = parent
    if p not in sys.path:
      sys.path.insert(0, p)
    from state_manager import mutate_state
    ready_event.set()
    go_event.wait(timeout=5.0)

    def _apply(state):
      state[key] = value

    mutate_state(_apply, path=_Path(path_str))

  def test_concurrent_writers_no_lost_update(self, tmp_path) -> None:
    '''REVIEWS HIGH #1: two processes both call mutate_state with non-
    conflicting mutations. The previous fcntl-on-save-only design lost
    one of the mutations because both processes loaded the SAME pre-lock
    snapshot. mutate_state closes the race: both mutations land.'''
    import multiprocessing as mp
    path = tmp_path / 'state.json'
    seed = reset_state()
    seed['account'] = 100000.0
    save_state(seed, path=path)

    ctx = mp.get_context('spawn')
    ready_a, ready_b = ctx.Event(), ctx.Event()
    go_a, go_b = ctx.Event(), ctx.Event()

    # Process A writes to 'last_run'; Process B writes to 'account'.
    proc_a = ctx.Process(
      target=self._subprocess_mutate,
      args=(str(path), 'last_run', '2026-04-25', ready_a, go_a),
    )
    proc_b = ctx.Process(
      target=self._subprocess_mutate,
      args=(str(path), 'account', 50000.0, ready_b, go_b),
    )
    proc_a.start()
    proc_b.start()
    try:
      assert ready_a.wait(timeout=5.0) and ready_b.wait(timeout=5.0)
      # Release both at the same time: lock contention is the key
      go_a.set()
      go_b.set()
    finally:
      proc_a.join(timeout=10.0)
      proc_b.join(timeout=10.0)
      if proc_a.is_alive():
        proc_a.terminate()
      if proc_b.is_alive():
        proc_b.terminate()

    final = load_state(path=path)
    # BOTH mutations must be visible (no lost update).
    assert final['last_run'] == '2026-04-25', (
      'REVIEWS HIGH #1: last_run mutation lost — '
      'mutate_state did not serialize load-mutate-save'
    )
    assert final['account'] == 50000.0, (
      'REVIEWS HIGH #1: account mutation lost — '
      'mutate_state did not serialize load-mutate-save'
    )

  def test_mutator_exception_releases_lock(self, tmp_path) -> None:
    '''A failing mutator must propagate the exception AND release the lock.
    State on disk should be unchanged (load_state's last successful read
    is the pre-mutate snapshot; save_state was never called).'''
    import fcntl
    from state_manager import mutate_state
    path = tmp_path / 'state.json'
    seed = reset_state()
    seed['account'] = 12345.0
    save_state(seed, path=path)

    def _broken(state):
      state['account'] = 99.0  # would mutate, but...
      raise ValueError('mutator boom')

    with pytest.raises(ValueError, match='mutator boom'):
      mutate_state(_broken, path=path)

    # Lock released
    fd = os.open(str(path), os.O_RDWR)
    try:
      fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
      fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
      os.close(fd)

    # State unchanged on disk (mutator's in-memory mutation never reached save_state)
    assert load_state(path=path)['account'] == 12345.0

  def test_reentrancy_save_state_within_mutate_state(self, tmp_path) -> None:
    '''A mutator that internally calls save_state(other_state, path=other_path)
    on a DIFFERENT file MUST succeed (independent inode -> independent flock
    namespace). For the SAME path, the mutate_state -> save_state nested call
    chain WOULD deadlock on POSIX flock-on-different-fd semantics; that is
    structurally avoided inside mutate_state via _save_state_unlocked. This
    test verifies the cross-file nesting case (legitimate use during a
    transient repair where the mutator writes a sidecar file).'''
    from state_manager import mutate_state
    path_outer = tmp_path / 'state.json'
    path_inner = tmp_path / 'other.json'
    save_state(reset_state(), path=path_outer)

    def _nest(state):
      state['account'] = 1.0
      # Nested save on a DIFFERENT path inside the outer lock — succeeds
      inner = reset_state()
      inner['account'] = 2.0
      save_state(inner, path=path_inner)

    mutate_state(_nest, path=path_outer)
    assert load_state(path=path_outer)['account'] == 1.0
    assert load_state(path=path_inner)['account'] == 2.0

  def test_returns_post_save_state(self, tmp_path) -> None:
    '''mutate_state returns the post-save state dict.'''
    from state_manager import mutate_state
    path = tmp_path / 'state.json'
    save_state(reset_state(), path=path)

    def _set(state):
      state['account'] = 42.0

    result = mutate_state(_set, path=path)
    assert isinstance(result, dict)
    assert result['account'] == 42.0


# =========================================================================
# Phase 14 D-09 — schema migration v2 -> v3 (Position.manual_stop backfill)
# =========================================================================

_V2_FIXTURE = Path('tests/fixtures/state_v2_no_manual_stop.json')


class TestSchemaMigrationV2ToV3:
  '''Phase 14 D-09: _migrate_v2_to_v3 backfills manual_stop=None on every
  non-None Position dict in state['positions'].

  Round-trip discipline (RESEARCH §Pattern 11):
    load(v2 fixture) -> assert manual_stop is None on each position
      -> save_state -> re-load -> assert schema_version == 3 +
      manual_stop preserved.

  Fixture: tests/fixtures/state_v2_no_manual_stop.json — schema_version=2
  with two open positions and NO manual_stop key.
  '''

  def test_v2_fixture_loads_with_manual_stop_backfilled_on_open_positions(
      self, tmp_path) -> None:
    '''Load v2 fixture; both open positions have manual_stop=None added.'''
    # Copy fixture into tmp_path so load_state's corruption-recovery + save
    # writes don't mutate the committed fixture file.
    import shutil
    target = tmp_path / 'state.json'
    shutil.copyfile(_V2_FIXTURE, target)
    state = load_state(path=target)
    assert state['schema_version'] == STATE_SCHEMA_VERSION, (
      f'Phase 14 D-09 + Phase 22 D-04: load_state must walk v2 forward to '
      f'STATE_SCHEMA_VERSION (now {STATE_SCHEMA_VERSION}); '
      f'got {state["schema_version"]}'
    )
    spi = state['positions']['SPI200']
    audusd = state['positions']['AUDUSD']
    assert spi is not None and audusd is not None
    assert 'manual_stop' in spi, (
      f'D-09: SPI200 manual_stop key missing post-migration; pos={spi}'
    )
    assert spi['manual_stop'] is None, (
      f'D-09: SPI200 manual_stop must default to None; got {spi["manual_stop"]!r}'
    )
    assert audusd['manual_stop'] is None, (
      f'D-09: AUDUSD manual_stop must default to None; got {audusd["manual_stop"]!r}'
    )

  def test_save_then_load_v3_round_trips(self, tmp_path) -> None:
    '''Load v2 -> save -> re-load yields schema_version=STATE_SCHEMA_VERSION
    with manual_stop=None preserved (Phase 14 D-09 invariant survives the
    Phase 22 v3 -> v4 bump).'''
    import shutil
    target = tmp_path / 'state.json'
    shutil.copyfile(_V2_FIXTURE, target)
    state = load_state(path=target)
    save_state(state, path=target)
    reloaded = load_state(path=target)
    assert reloaded['schema_version'] == STATE_SCHEMA_VERSION
    assert reloaded['positions']['SPI200']['manual_stop'] is None
    assert reloaded['positions']['AUDUSD']['manual_stop'] is None

  def test_migration_idempotent(self) -> None:
    '''Applying _migrate_v2_to_v3 twice produces identical output.'''
    from state_manager import _migrate_v2_to_v3
    s = {
      'positions': {
        'SPI200': {'entry_price': 7800.0, 'direction': 'LONG'},
        'AUDUSD': None,
      },
    }
    once = _migrate_v2_to_v3(s)
    twice = _migrate_v2_to_v3(once)
    assert once == twice, (
      f'D-09 idempotency: once={once!r} twice={twice!r}'
    )

  def test_migration_preserves_existing_manual_stop(self) -> None:
    '''Pre-existing manual_stop=7700.0 is NOT overwritten to None.'''
    from state_manager import _migrate_v2_to_v3
    s = {
      'positions': {
        'SPI200': {
          'entry_price': 7800.0,
          'direction': 'LONG',
          'manual_stop': 7700.0,
        },
      },
    }
    out = _migrate_v2_to_v3(s)
    assert out['positions']['SPI200']['manual_stop'] == 7700.0, (
      f'D-09: existing manual_stop=7700.0 must be preserved; '
      f'got {out["positions"]["SPI200"]["manual_stop"]!r}'
    )

  def test_none_position_stays_none(self) -> None:
    '''Position slots with value None remain None (no dict to backfill).'''
    from state_manager import _migrate_v2_to_v3
    s = {'positions': {'SPI200': None, 'AUDUSD': None}}
    out = _migrate_v2_to_v3(s)
    assert out['positions']['SPI200'] is None
    assert out['positions']['AUDUSD'] is None

  def test_v3_open_position_round_trips_through_save_state(self, tmp_path) -> None:
    '''In-memory v3 with manual_stop=7700.0 saves+reloads bit-identically.'''
    path = tmp_path / 'state.json'
    state = reset_state()
    state['positions']['SPI200'] = {
      'direction': 'LONG',
      'entry_price': 7800.0,
      'entry_date': '2026-04-15',
      'n_contracts': 1,
      'pyramid_level': 0,
      'peak_price': 7900.0,
      'trough_price': None,
      'atr_entry': 50.0,
      'manual_stop': 7700.0,
    }
    save_state(state, path=path)
    reloaded = load_state(path=path)
    assert reloaded['positions']['SPI200']['manual_stop'] == 7700.0, (
      'v3 round-trip: manual_stop=7700.0 must persist + reload'
    )
    assert reloaded['schema_version'] == STATE_SCHEMA_VERSION


# =========================================================================
# Phase 22 — _migrate_v3_to_v4 (strategy_version backfill on signal rows)
# =========================================================================

class TestMigrateV3ToV4:
  '''Phase 22 D-04 / D-05: _migrate_v3_to_v4 backfills strategy_version on
  every dict-shaped signal row. Stamps 'v1.1.0' on existing rows (rows on
  the droplet at first v1.2 deploy were produced under v1.1 logic).

  Invariants:
    - additive: every pre-existing field on each signal row preserved
    - idempotent: rows that already carry strategy_version are NOT overwritten
    - skip int-shape: Phase 3 reset_state legacy `signals: {SPI200: 0}` shape
      is left untouched (only dict-shaped rows are migrated)
  '''

  def test_migrate_v3_to_v4_backfills_existing_signal_rows(self) -> None:
    '''D-05: every dict-shaped signal row gets strategy_version='v1.1.0'.'''
    from state_manager import _migrate_v3_to_v4
    s = {
      'schema_version': 3,
      'signals': {
        'SPI200': {
          'signal': 1,
          'signal_as_of': '2026-04-29',
          'as_of_run': '2026-04-29',
        },
        'AUDUSD': {
          'signal': -1,
          'signal_as_of': '2026-04-29',
          'as_of_run': '2026-04-29',
        },
      },
    }
    out = _migrate_v3_to_v4(s)
    assert out['signals']['SPI200']['strategy_version'] == 'v1.1.0', (
      f'D-05: SPI200 must be stamped v1.1.0 on first v1.2 load; '
      f'got {out["signals"]["SPI200"].get("strategy_version")!r}'
    )
    assert out['signals']['AUDUSD']['strategy_version'] == 'v1.1.0', (
      f'D-05: AUDUSD must be stamped v1.1.0 on first v1.2 load; '
      f'got {out["signals"]["AUDUSD"].get("strategy_version")!r}'
    )

  def test_migrate_v3_to_v4_via_full_migrate_sets_schema_current(self, tmp_path) -> None:
    '''Going through _migrate (the dispatch walker) on a v3 state ends at
    STATE_SCHEMA_VERSION (currently 5 after Phase 17 D-08) AND backfills
    strategy_version='v1.1.0' on existing rows.
    '''
    from state_manager import _migrate
    s = {
      'schema_version': 3,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {
        'SPI200': {'signal': 1, 'signal_as_of': '2026-04-29', 'as_of_run': '2026-04-29'},
        'AUDUSD': {'signal': 0, 'signal_as_of': '2026-04-29', 'as_of_run': '2026-04-29'},
      },
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': INITIAL_ACCOUNT,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
    }
    out = _migrate(s)
    assert out['schema_version'] == STATE_SCHEMA_VERSION, (
      f'Phase 22/17: _migrate must walk v3 -> {STATE_SCHEMA_VERSION}; '
      f'got {out["schema_version"]}'
    )
    assert out['signals']['SPI200']['strategy_version'] == 'v1.1.0'
    assert out['signals']['AUDUSD']['strategy_version'] == 'v1.1.0'

  def test_migrate_v3_to_v4_preserves_other_signal_fields(self) -> None:
    '''Round-trip equality: every original key on each signal row preserved
    with its exact value; only strategy_version is added.
    '''
    from state_manager import _migrate_v3_to_v4
    original_spi = {
      'signal': 1,
      'signal_as_of': '2026-04-29',
      'as_of_run': '2026-04-29',
      'last_close': 1234.5,
      'last_scalars': {'adx': 25.0, 'mom_1': 0.01, 'mom_3': 0.02, 'rvol': 1.1},
    }
    s = {'schema_version': 3, 'signals': {'SPI200': dict(original_spi)}}
    out = _migrate_v3_to_v4(s)
    sig = out['signals']['SPI200']
    # Original keys preserved with exact values.
    for k, v in original_spi.items():
      assert sig[k] == v, (
        f'D-05 additive guarantee violated: signals.SPI200.{k} changed '
        f'from {v!r} to {sig.get(k)!r}'
      )
    # New field present.
    assert sig['strategy_version'] == 'v1.1.0'
    # No extra keys beyond original + strategy_version.
    assert set(sig.keys()) == set(original_spi.keys()) | {'strategy_version'}

  def test_migrate_v3_to_v4_idempotent(self) -> None:
    '''Re-running _migrate_v3_to_v4 on already-migrated data does NOT
    overwrite an existing strategy_version field (preserves the existing
    value — supports replayed migrations and manual state.json edits).
    '''
    from state_manager import _migrate_v3_to_v4
    s = {
      'schema_version': 4,
      'signals': {
        'SPI200': {'signal': 1, 'strategy_version': 'v1.2.0'},
      },
    }
    out_once = _migrate_v3_to_v4(s)
    out_twice = _migrate_v3_to_v4(out_once)
    assert out_once['signals']['SPI200']['strategy_version'] == 'v1.2.0', (
      'idempotency: existing v1.2.0 must be preserved (not overwritten to v1.1.0)'
    )
    assert out_once == out_twice, (
      f'idempotency: once={out_once!r} twice={out_twice!r}'
    )

  def test_migrate_v3_to_v4_handles_int_signal_legacy_shape(self) -> None:
    '''Phase 3 reset_state legacy int shape (signals.SPI200 = 0) MUST NOT be
    rewritten by the migration — only dict-shaped rows carry strategy_version.
    main.py per D-08 upgrade branch (Pitfall 7) tolerates both shapes on read
    and always writes the dict shape on the next run.
    '''
    from state_manager import _migrate_v3_to_v4
    s = {
      'schema_version': 3,
      'signals': {'SPI200': 1, 'AUDUSD': 0},
    }
    out = _migrate_v3_to_v4(s)
    assert out['signals']['SPI200'] == 1, (
      f'int-shape SPI200 must stay int; got {out["signals"]["SPI200"]!r}'
    )
    assert out['signals']['AUDUSD'] == 0, (
      f'int-shape AUDUSD must stay int; got {out["signals"]["AUDUSD"]!r}'
    )

  def test_migrate_v3_to_v4_skips_signal_rows_with_existing_field(self) -> None:
    '''A row that already carries strategy_version='v1.0.0' is preserved —
    the migration MUST NOT overwrite to 'v1.1.0'.
    '''
    from state_manager import _migrate_v3_to_v4
    s = {
      'schema_version': 3,
      'signals': {
        'SPI200': {'signal': 1, 'strategy_version': 'v1.0.0'},
      },
    }
    out = _migrate_v3_to_v4(s)
    assert out['signals']['SPI200']['strategy_version'] == 'v1.0.0', (
      f'D-05 idempotent rule: existing v1.0.0 must not be overwritten; '
      f'got {out["signals"]["SPI200"]["strategy_version"]!r}'
    )

  def test_full_walk_v0_to_v4_then_load_state(self, tmp_path) -> None:
    '''End-to-end walk: write a state with no schema_version (-> v0) to disk,
    call load_state, assert returned state at STATE_SCHEMA_VERSION (=4) and
    the signal rows (if dict-shaped) carry strategy_version='v1.1.0'.

    Uses a v0 state with dict-shaped signals so the v3->v4 migration has
    something to operate on (Phase 3 reset_state would emit int-shape; we
    construct a richer test fixture here).
    '''
    path = tmp_path / 'state.json'
    bare_state = {
      # no schema_version → defaults to 0
      'account': INITIAL_ACCOUNT, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {
        'SPI200': {
          'signal': 1, 'signal_as_of': '2026-04-29',
          'as_of_run': '2026-04-29',
        },
        'AUDUSD': {
          'signal': 0, 'signal_as_of': '2026-04-29',
          'as_of_run': '2026-04-29',
        },
      },
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    path.write_text(json.dumps(bare_state, indent=2))
    loaded = load_state(path=path)
    # Phase 17 D-08: STATE_SCHEMA_VERSION was 5; Phase 19 bumped to 6.
    # Guard: value must be >= 5 (was 5 at Phase 17; Phase 19 bumped to 6).
    assert loaded['schema_version'] >= 5, (
      f'walk-forward chain v0->...->current must be >= 5; '
      f'got {loaded["schema_version"]}'
    )
    assert loaded['schema_version'] == STATE_SCHEMA_VERSION, (
      f'walk-forward must reach STATE_SCHEMA_VERSION={STATE_SCHEMA_VERSION}; '
      f'got {loaded["schema_version"]}'
    )
    assert loaded['signals']['SPI200']['strategy_version'] == 'v1.1.0'
    assert loaded['signals']['AUDUSD']['strategy_version'] == 'v1.1.0'

  def test_defensive_read_logs_WARN_on_missing_strategy_version(self, caplog) -> None:
    '''D-06 belt-and-suspenders: _read_signal_strategy_version returns 'v1.0.0'
    AND emits a [State] WARN log when the strategy_version field is absent.
    '''
    import logging as _logging
    from state_manager import _read_signal_strategy_version
    caplog.set_level(_logging.WARNING, logger='state_manager')
    sig_without = {'signal': 1, 'signal_as_of': '2026-04-29'}
    out = _read_signal_strategy_version(sig_without)
    assert out == 'v1.0.0', (
      f'D-06 default: missing field must default to v1.0.0; got {out!r}'
    )
    warn_records = [
      r for r in caplog.records
      if r.levelname == 'WARNING'
      and 'strategy_version' in r.getMessage()
    ]
    assert len(warn_records) == 1, (
      f'D-06: exactly one WARN must be emitted on missing strategy_version; '
      f'got {len(warn_records)} (records={[r.getMessage() for r in warn_records]!r})'
    )
    assert '[State] WARN signal row missing strategy_version field' in (
      warn_records[0].getMessage()
    ), (
      f'D-06: WARN message text must follow the [State] log-prefix convention; '
      f'got {warn_records[0].getMessage()!r}'
    )

  def test_defensive_read_returns_existing_value_without_warn(self, caplog) -> None:
    '''D-06 happy path: when strategy_version is present, return it and
    DO NOT emit a WARN (avoids journalctl noise on every read).
    '''
    import logging as _logging
    from state_manager import _read_signal_strategy_version
    caplog.set_level(_logging.WARNING, logger='state_manager')
    sig_with = {'signal': 1, 'strategy_version': 'v1.2.0'}
    out = _read_signal_strategy_version(sig_with)
    assert out == 'v1.2.0'
    strategy_warns = [
      r for r in caplog.records
      if r.levelname == 'WARNING'
      and 'strategy_version' in r.getMessage()
    ]
    assert strategy_warns == [], (
      f'D-06: present field must NOT emit WARN; '
      f'got {[r.getMessage() for r in strategy_warns]!r}'
    )


class TestMigrateV4ToV5:
  '''Phase 17 D-08: _migrate_v4_to_v5 backfills ohlc_window=[] +
  indicator_scalars={} on existing dict-shaped signal rows.

  Invariants (mirror of TestMigrateV3ToV4):
    - additive: every pre-existing field on each signal row preserved
    - idempotent: rows that already carry ohlc_window / indicator_scalars
      are NOT overwritten (two independent guards)
    - partial-state: missing only one of the two fields → missing one backfilled,
      present one preserved (proves the two guards are independent)
    - skip int-shape: Phase 3 reset_state legacy int rows left untouched
  '''

  def test_migrate_v4_to_v5_backfills_existing_signal_rows(self) -> None:
    '''D-08: every dict-shaped signal row gets ohlc_window=[] AND
    indicator_scalars={} when those fields are absent.
    '''
    from state_manager import _migrate_v4_to_v5
    s = {
      'schema_version': 4,
      'signals': {
        'SPI200': {
          'signal': 1,
          'signal_as_of': '2026-04-29',
          'as_of_run': '2026-04-29',
          'last_close': 1234.5,
          'last_scalars': {'adx': 25.0},
          'strategy_version': 'v1.2.0',
        },
        'AUDUSD': {
          'signal': -1,
          'signal_as_of': '2026-04-29',
          'as_of_run': '2026-04-29',
          'last_close': 0.6543,
          'last_scalars': {'adx': 20.0},
          'strategy_version': 'v1.2.0',
        },
      },
    }
    out = _migrate_v4_to_v5(s)
    assert out['signals']['SPI200']['ohlc_window'] == [], (
      f'D-08: SPI200 must be stamped ohlc_window=[] on first v1.2.x load; '
      f'got {out["signals"]["SPI200"].get("ohlc_window")!r}'
    )
    assert out['signals']['SPI200']['indicator_scalars'] == {}, (
      f'D-08: SPI200 must be stamped indicator_scalars={{}} on first v1.2.x load; '
      f'got {out["signals"]["SPI200"].get("indicator_scalars")!r}'
    )
    assert out['signals']['AUDUSD']['ohlc_window'] == [], (
      f'D-08: AUDUSD must be stamped ohlc_window=[] on first v1.2.x load; '
      f'got {out["signals"]["AUDUSD"].get("ohlc_window")!r}'
    )
    assert out['signals']['AUDUSD']['indicator_scalars'] == {}, (
      f'D-08: AUDUSD must be stamped indicator_scalars={{}} on first v1.2.x load; '
      f'got {out["signals"]["AUDUSD"].get("indicator_scalars")!r}'
    )

  def test_migrate_v4_to_v5_via_full_migrate_sets_schema_5(self) -> None:
    '''Going through _migrate (the dispatch walker) on a v4 state ends at
    schema_version=5 AND backfills ohlc_window=[] + indicator_scalars={}.
    '''
    from state_manager import _migrate
    s = {
      'schema_version': 4,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {
        'SPI200': {
          'signal': 1,
          'signal_as_of': '2026-04-29',
          'as_of_run': '2026-04-29',
          'strategy_version': 'v1.2.0',
        },
        'AUDUSD': {
          'signal': 0,
          'signal_as_of': '2026-04-29',
          'as_of_run': '2026-04-29',
          'strategy_version': 'v1.2.0',
        },
      },
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': INITIAL_ACCOUNT,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
    }
    out = _migrate(s)
    # Phase 17: was == 5; Phase 19 bumped to 6 — v4 now walks to 6 (passes v5 too).
    assert out['schema_version'] >= 5, (
      f'Phase 17 D-08: _migrate must walk v4 -> at least v5; got {out["schema_version"]}'
    )
    assert out['signals']['SPI200']['ohlc_window'] == []
    assert out['signals']['SPI200']['indicator_scalars'] == {}
    assert out['signals']['AUDUSD']['ohlc_window'] == []
    assert out['signals']['AUDUSD']['indicator_scalars'] == {}

  def test_migrate_v4_to_v5_preserves_other_signal_fields(self) -> None:
    '''Round-trip equality: every original key on each signal row preserved
    with its exact value; only ohlc_window and indicator_scalars are added.
    '''
    from state_manager import _migrate_v4_to_v5
    original_spi = {
      'signal': 1,
      'signal_as_of': '2026-04-29',
      'as_of_run': '2026-04-29',
      'last_close': 1234.5,
      'last_scalars': {'adx': 25.0, 'mom1': 0.01},
      'strategy_version': 'v1.2.0',
    }
    s = {'schema_version': 4, 'signals': {'SPI200': dict(original_spi)}}
    out = _migrate_v4_to_v5(s)
    sig = out['signals']['SPI200']
    # Original keys preserved with exact values.
    for k, v in original_spi.items():
      assert sig[k] == v, (
        f'D-08 additive guarantee violated: signals.SPI200.{k} changed '
        f'from {v!r} to {sig.get(k)!r}'
      )
    # New fields present.
    assert sig['ohlc_window'] == []
    assert sig['indicator_scalars'] == {}
    # Exactly the right set of keys.
    assert set(sig.keys()) == set(original_spi.keys()) | {'ohlc_window', 'indicator_scalars'}

  def test_migrate_v4_to_v5_idempotent_ohlc_window_already_populated(self) -> None:
    '''Re-running _migrate_v4_to_v5 when ohlc_window is already populated does
    NOT overwrite (preserves the existing list).
    '''
    from state_manager import _migrate_v4_to_v5
    existing_window = [{'date': '2026-04-29', 'open': 100.0, 'high': 101.0,
                        'low': 99.0, 'close': 100.5}]
    s = {
      'schema_version': 5,
      'signals': {
        'SPI200': {
          'signal': 1,
          'ohlc_window': existing_window,
          'indicator_scalars': {'atr': 0.012},
        },
      },
    }
    out = _migrate_v4_to_v5(s)
    assert out['signals']['SPI200']['ohlc_window'] == existing_window, (
      'idempotency: populated ohlc_window must not be overwritten with []'
    )

  def test_migrate_v4_to_v5_idempotent_indicator_scalars_already_populated(self) -> None:
    '''Re-running _migrate_v4_to_v5 when indicator_scalars is already populated
    does NOT overwrite (preserves the existing dict).
    '''
    from state_manager import _migrate_v4_to_v5
    existing_scalars = {'atr': 0.012, 'adx': 25.0}
    s = {
      'schema_version': 5,
      'signals': {
        'SPI200': {
          'signal': 1,
          'ohlc_window': [],
          'indicator_scalars': existing_scalars,
        },
      },
    }
    out = _migrate_v4_to_v5(s)
    assert out['signals']['SPI200']['indicator_scalars'] == existing_scalars, (
      'idempotency: populated indicator_scalars must not be overwritten with {}'
    )

  def test_migrate_v4_to_v5_idempotent_partial_state(self) -> None:
    '''A row with ohlc_window present (even empty []) but no indicator_scalars:
    ohlc_window is preserved, indicator_scalars is backfilled.
    Proves the two "field not in sig" guards are INDEPENDENT.
    '''
    from state_manager import _migrate_v4_to_v5
    s = {
      'schema_version': 4,
      'signals': {
        'SPI200': {
          'signal': 1,
          'ohlc_window': [],   # key present, value empty — must be preserved
          # indicator_scalars absent — must be backfilled
        },
      },
    }
    out = _migrate_v4_to_v5(s)
    sig = out['signals']['SPI200']
    # ohlc_window key was present — must be the SAME empty list (not overwritten)
    assert 'ohlc_window' in sig
    assert sig['ohlc_window'] == [], (
      'partial-state: ohlc_window=[] (key present) must be preserved, not re-stamped'
    )
    # indicator_scalars was missing — must be backfilled to {}
    assert sig['indicator_scalars'] == {}, (
      'partial-state: missing indicator_scalars must be backfilled to {}'
    )

  def test_migrate_v4_to_v5_skips_int_legacy_shape(self) -> None:
    '''Phase 3 reset_state legacy int shape (signals.SPI200 = 1) MUST NOT be
    rewritten by the migration — only dict-shaped rows carry ohlc_window.
    '''
    from state_manager import _migrate_v4_to_v5
    s = {
      'schema_version': 4,
      'signals': {'SPI200': 1, 'AUDUSD': 0},
    }
    out = _migrate_v4_to_v5(s)
    assert out['signals']['SPI200'] == 1, (
      f'int-shape SPI200 must stay int; got {out["signals"]["SPI200"]!r}'
    )
    assert out['signals']['AUDUSD'] == 0, (
      f'int-shape AUDUSD must stay int; got {out["signals"]["AUDUSD"]!r}'
    )


class TestFullWalkV0ToV5:
  '''End-to-end migration walk from v0 (no schema_version key) all the way to
  v5. Proves the full chain v0→v1→v2→v3→v4→v5 is registered and functional.
  '''

  def test_full_walk_v0_to_v5_then_load_state(self, tmp_path) -> None:
    '''Write a state with no schema_version (v0) to disk, call load_state,
    assert returned state has schema_version==5 AND:
    - strategy_version=='v1.1.0' (Phase 22 v3->v4 backfill)
    - ohlc_window==[] (Phase 17 v4->v5 backfill)
    - indicator_scalars=={} (Phase 17 v4->v5 backfill)

    Uses a v0 state with dict-shaped signals so both migrations have
    something to operate on.
    '''
    path = tmp_path / 'state.json'
    bare_state = {
      # no schema_version → defaults to 0
      'account': INITIAL_ACCOUNT, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {
        'SPI200': {
          'signal': 1, 'signal_as_of': '2026-04-29',
          'as_of_run': '2026-04-29',
        },
        'AUDUSD': {
          'signal': 0, 'signal_as_of': '2026-04-29',
          'as_of_run': '2026-04-29',
        },
      },
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    import json as _json
    path.write_text(_json.dumps(bare_state, indent=2))
    loaded = load_state(path=path)
    # Phase 17 D-08: was == 5; Phase 19 bumped STATE_SCHEMA_VERSION to 6.
    # Guard: full walk must reach current STATE_SCHEMA_VERSION.
    assert loaded['schema_version'] >= 5, (
      f'walk-forward chain v0->...->current must be >= 5; '
      f'got {loaded["schema_version"]}'
    )
    assert loaded['schema_version'] == STATE_SCHEMA_VERSION, (
      f'walk-forward must reach STATE_SCHEMA_VERSION={STATE_SCHEMA_VERSION}; '
      f'got {loaded["schema_version"]}'
    )
    # Phase 22 v3->v4 backfill also ran
    assert loaded['signals']['SPI200']['strategy_version'] == 'v1.1.0'
    assert loaded['signals']['AUDUSD']['strategy_version'] == 'v1.1.0'
    # Phase 17 v4->v5 backfill
    assert loaded['signals']['SPI200']['ohlc_window'] == []
    assert loaded['signals']['SPI200']['indicator_scalars'] == {}
    assert loaded['signals']['AUDUSD']['ohlc_window'] == []
    assert loaded['signals']['AUDUSD']['indicator_scalars'] == {}


class TestMigrateV5ToV6:
  '''Phase 19 D-08: _migrate_v5_to_v6 backfills paper_trades=[] at top level.

  Invariants (mirror of TestMigrateV4ToV5):
    - backfill: v5 state without paper_trades key gets paper_trades=[]
    - idempotent: existing populated paper_trades array preserved (NOT overwritten)
    - idempotent via full _migrate walker: already-v6 state is a no-op
    - via full _migrate: v5 state walks to schema_version=6
    - additive: all pre-existing top-level fields survive unchanged
    - full v0->v6 walk via load_state: entire migration chain functional
  '''

  def test_migrate_v5_to_v6_backfills_paper_trades_when_absent(self) -> None:
    '''D-08: v5 state missing paper_trades key gets paper_trades=[] stamped
    after migration AND schema_version advances to 6.
    '''
    from state_manager import _migrate, _migrate_v5_to_v6
    s = {
      'schema_version': 5,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': INITIAL_ACCOUNT,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
    }
    # Direct function: _migrate_v5_to_v6 adds paper_trades=[]
    out = _migrate_v5_to_v6(dict(s))
    assert 'paper_trades' in out, (
      'D-08: _migrate_v5_to_v6 must stamp paper_trades on state dict'
    )
    assert out['paper_trades'] == [], (
      f'D-08: paper_trades must be empty list; got {out["paper_trades"]!r}'
    )
    # Via _migrate walker: schema_version advances to STATE_SCHEMA_VERSION (7 at Phase 20)
    out2 = _migrate(dict(s))
    assert out2['schema_version'] == STATE_SCHEMA_VERSION, (
      f'D-08: _migrate must walk v5->v{STATE_SCHEMA_VERSION}; got {out2["schema_version"]}'
    )
    assert out2['paper_trades'] == [], (
      f'D-08: walker must stamp paper_trades=[]; got {out2["paper_trades"]!r}'
    )

  def test_migrate_v5_to_v6_preserves_other_top_level_fields(self) -> None:
    '''Round-trip equality: every original top-level key+value is preserved
    with its exact value; only paper_trades is added.
    '''
    from state_manager import _migrate_v5_to_v6
    original = {
      'schema_version': 5,
      'account': 123456.78,
      'last_run': '2026-04-30',
      'positions': {'SPI200': None, 'AUDUSD': {'direction': 'LONG', 'entry_price': 7800.0}},
      'signals': {'SPI200': {'signal': 1}, 'AUDUSD': {'signal': -1}},
      'trade_log': [{'id': 'T1'}],
      'equity_history': [{'date': '2026-04-01', 'equity': 100000.0}],
      'warnings': ['warn1'],
      'initial_account': 100000.0,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
    }
    out = _migrate_v5_to_v6(dict(original))
    for key, value in original.items():
      assert out[key] == value, (
        f'D-08: field {key!r} must be preserved; expected {value!r}, got {out[key]!r}'
      )
    assert out['paper_trades'] == [], (
      f'D-08: paper_trades must be [] on first backfill; got {out["paper_trades"]!r}'
    )

  def test_migrate_v5_to_v6_idempotent_paper_trades_already_populated(self) -> None:
    '''Running _migrate_v5_to_v6 directly on an already-v6 state with a
    populated paper_trades array MUST NOT overwrite the existing rows.
    '''
    from state_manager import _migrate_v5_to_v6
    existing_row = {
      'id': 'SPI200-20260430-001', 'instrument': 'SPI200', 'side': 'LONG',
      'status': 'open',
    }
    s = {
      'schema_version': 6,
      'paper_trades': [existing_row],
    }
    out = _migrate_v5_to_v6(dict(s))
    assert len(out['paper_trades']) == 1, (
      f'D-08: idempotent — populated paper_trades must be preserved; '
      f'got {out["paper_trades"]!r}'
    )
    assert out['paper_trades'][0] == existing_row, (
      'D-08: idempotent — row data must be unchanged'
    )

  def test_migrate_v5_to_v6_idempotent_via_full_migrate(self) -> None:
    '''Running _migrate on an already-v6 state with a populated paper_trades
    array walks forward to current STATE_SCHEMA_VERSION; paper_trades preserved.
    (Phase 20: walker now goes to v7; idempotent guard in v6->v7 preserves the
    existing row's lack of last_alert_state=None.)
    '''
    from state_manager import _migrate
    existing_row = {
      'id': 'SPI200-20260430-001', 'instrument': 'SPI200', 'side': 'LONG',
      'status': 'open',
    }
    s = {
      'schema_version': 6,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': INITIAL_ACCOUNT,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
      'paper_trades': [existing_row],
    }
    out = _migrate(dict(s))
    assert out['schema_version'] == STATE_SCHEMA_VERSION, (
      f'D-08: v6 state walks to {STATE_SCHEMA_VERSION}; got {out["schema_version"]}'
    )
    assert len(out['paper_trades']) == 1, (
      'D-08: existing rows must survive the walk'
    )
    # Phase 20 v6->v7 migration adds last_alert_state=None to the row
    assert out['paper_trades'][0]['id'] == existing_row['id']
    assert out['paper_trades'][0]['last_alert_state'] is None

  def test_migrate_v5_to_v6_via_full_migrate_sets_schema_6(self) -> None:
    '''Going through _migrate (the dispatch walker) on a v5 state ends at
    STATE_SCHEMA_VERSION AND stamps paper_trades=[].
    (Phase 20: walker walks v5 -> v6 -> v7 = STATE_SCHEMA_VERSION.)
    '''
    from state_manager import _migrate
    s = {
      'schema_version': 5,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': INITIAL_ACCOUNT,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
    }
    out = _migrate(dict(s))
    assert out['schema_version'] == STATE_SCHEMA_VERSION, (
      f'Phase 19 D-08: _migrate must walk v5->{STATE_SCHEMA_VERSION}; got {out["schema_version"]}'
    )
    assert out.get('paper_trades') == [], (
      f'D-08: walker must stamp paper_trades=[]; got {out.get("paper_trades")!r}'
    )


class TestFullWalkV0ToV6:
  '''End-to-end migration walk from v0 (no schema_version key) all the way to
  STATE_SCHEMA_VERSION (v7 at Phase 20; was v6 at Phase 19).
  Proves the full chain v0→v1→v2→v3→v4→v5→v6→v7 is registered and functional.
  '''

  def test_full_walk_v0_to_v6_then_load_state(self, tmp_path) -> None:
    '''Write a state with no schema_version (v0) to disk, call load_state,
    assert returned state has schema_version==STATE_SCHEMA_VERSION AND:
    - strategy_version=='v1.1.0' (Phase 22 v3->v4 backfill)
    - ohlc_window==[] (Phase 17 v4->v5 backfill)
    - indicator_scalars=={} (Phase 17 v4->v5 backfill)
    - paper_trades==[] (Phase 19 v5->v6 backfill)

    Uses a v0 state with dict-shaped signals so all migrations have
    something to operate on.
    '''
    path = tmp_path / 'state.json'
    bare_state = {
      # no schema_version → defaults to 0
      'account': INITIAL_ACCOUNT, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {
        'SPI200': {
          'signal': 1, 'signal_as_of': '2026-04-30',
          'as_of_run': '2026-04-30',
        },
        'AUDUSD': {
          'signal': 0, 'signal_as_of': '2026-04-30',
          'as_of_run': '2026-04-30',
        },
      },
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    import json as _json
    path.write_text(_json.dumps(bare_state, indent=2))
    loaded = load_state(path=path)
    assert loaded['schema_version'] == STATE_SCHEMA_VERSION == 7, (
      f'walk-forward chain v0->...->v7 must end at 7; '
      f'got {loaded["schema_version"]}'
    )
    # Phase 22 v3->v4 backfill also ran
    assert loaded['signals']['SPI200']['strategy_version'] == 'v1.1.0'
    assert loaded['signals']['AUDUSD']['strategy_version'] == 'v1.1.0'
    # Phase 17 v4->v5 backfill
    assert loaded['signals']['SPI200']['ohlc_window'] == []
    assert loaded['signals']['SPI200']['indicator_scalars'] == {}
    assert loaded['signals']['AUDUSD']['ohlc_window'] == []
    assert loaded['signals']['AUDUSD']['indicator_scalars'] == {}
    # Phase 19 v5->v6 backfill
    assert loaded.get('paper_trades') == [], (
      f'Phase 19: full v0->v6 walk must stamp paper_trades=[]; '
      f'got {loaded.get("paper_trades")!r}'
    )


class TestMigrateV6ToV7:
  '''Phase 20 D-08: _migrate_v6_to_v7 backfills last_alert_state=None on
  existing paper_trades rows.

  Invariants (mirror of TestMigrateV5ToV6):
    - backfill: v6 rows missing last_alert_state get last_alert_state=None
    - preserves_other_fields: all pre-existing paper_trades row fields survive
    - idempotent: existing last_alert_state value NOT overwritten on re-run
    - skips_non_dict_rows: malformed entries (str, None, int) unchanged
    - no_paper_trades_key: missing key is a no-op (s.get('paper_trades', []))
    - silent: no log line, no warnings append (D-15 silent migration)
    - full v0->v7 walk via load_state: entire migration chain functional
  '''

  def test_migrate_v6_to_v7_backfills_last_alert_state_on_existing_rows(self) -> None:
    '''D-08: v6 state with paper_trades rows missing last_alert_state gets
    last_alert_state=None stamped on each dict-shaped row AND schema_version
    advances to 7 via _migrate walker.
    '''
    from state_manager import _migrate, _migrate_v6_to_v7
    row1 = {'id': 'SPI200-20260430-001', 'instrument': 'SPI200', 'side': 'LONG',
             'status': 'open'}
    row2 = {'id': 'AUDUSD-20260430-001', 'instrument': 'AUDUSD', 'side': 'SHORT',
             'status': 'open'}
    s = {
      'schema_version': 6,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {},
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'initial_account': INITIAL_ACCOUNT,
      'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'},
      'paper_trades': [dict(row1), dict(row2)],
    }
    # Direct function: _migrate_v6_to_v7 stamps last_alert_state=None
    out = _migrate_v6_to_v7(dict(s))
    assert out['paper_trades'][0]['last_alert_state'] is None, (
      'D-08: _migrate_v6_to_v7 must stamp last_alert_state=None on row 0'
    )
    assert out['paper_trades'][1]['last_alert_state'] is None, (
      'D-08: _migrate_v6_to_v7 must stamp last_alert_state=None on row 1'
    )
    # Via _migrate walker: schema_version advances to 7
    out2 = _migrate(dict(s))
    assert out2['schema_version'] == 7, (
      f'D-08: _migrate must walk v6->v7; got {out2["schema_version"]}'
    )
    assert out2['paper_trades'][0]['last_alert_state'] is None
    assert out2['paper_trades'][1]['last_alert_state'] is None

  def test_migrate_v6_to_v7_preserves_other_paper_trade_fields(self) -> None:
    '''Round-trip equality: every original paper_trades row key+value is
    preserved; only last_alert_state is added (additive, not destructive).
    '''
    from state_manager import _migrate_v6_to_v7
    original_row = {
      'id': 'SPI200-20260430-001',
      'instrument': 'SPI200',
      'side': 'LONG',
      'entry_dt': '2026-04-30T08:00:00+08:00',
      'entry_price': 8200.0,
      'contracts': 1,
      'stop_price': 8100.0,
      'entry_cost_aud': 3.0,
      'status': 'open',
      'exit_dt': None,
      'exit_price': None,
      'realised_pnl': None,
      'strategy_version': 'v1.2.0',
    }
    s = {
      'schema_version': 6,
      'paper_trades': [dict(original_row)],
    }
    out = _migrate_v6_to_v7(dict(s))
    result_row = out['paper_trades'][0]
    # Every original field is preserved exactly
    for key, value in original_row.items():
      assert result_row[key] == value, (
        f'D-08: field {key!r} must be preserved; expected {value!r}, got {result_row[key]!r}'
      )
    # New field added
    assert 'last_alert_state' in result_row, (
      'D-08: last_alert_state field must be added by migration'
    )
    assert result_row['last_alert_state'] is None

  def test_migrate_v6_to_v7_idempotent(self) -> None:
    '''Running _migrate_v6_to_v7 directly on a row already carrying
    last_alert_state=\'APPROACHING\' MUST NOT overwrite the existing value.
    The idempotent guard is: `if \'last_alert_state\' not in row`.
    '''
    from state_manager import _migrate_v6_to_v7
    existing_row = {
      'id': 'SPI200-20260430-001', 'instrument': 'SPI200', 'side': 'LONG',
      'status': 'open', 'last_alert_state': 'APPROACHING',
    }
    s = {
      'schema_version': 7,
      'paper_trades': [dict(existing_row)],
    }
    out = _migrate_v6_to_v7(dict(s))
    assert out['paper_trades'][0]['last_alert_state'] == 'APPROACHING', (
      'D-08: idempotent — existing last_alert_state must NOT be overwritten; '
      f'got {out["paper_trades"][0]["last_alert_state"]!r}'
    )

  def test_migrate_v6_to_v7_skips_non_dict_rows(self) -> None:
    '''Malformed paper_trades entries (str, None, int) are skipped by the
    defensive isinstance(row, dict) guard; only the dict-shaped row is touched.
    '''
    from state_manager import _migrate_v6_to_v7
    valid_row = {'id': 'SPI200-20260430-001', 'instrument': 'SPI200',
                 'side': 'LONG', 'status': 'open'}
    s = {
      'schema_version': 6,
      'paper_trades': [dict(valid_row), 'not a dict', None, 42],
    }
    out = _migrate_v6_to_v7(dict(s))
    assert out['paper_trades'][0]['last_alert_state'] is None, (
      'D-08: dict-shaped row must get last_alert_state=None'
    )
    assert out['paper_trades'][1] == 'not a dict', (
      'D-08: non-dict entries must be untouched'
    )
    assert out['paper_trades'][2] is None
    assert out['paper_trades'][3] == 42

  def test_migrate_v6_to_v7_no_paper_trades_key(self) -> None:
    '''State missing the paper_trades key entirely is handled defensively via
    s.get(\'paper_trades\', []). Migration is a no-op; schema_version still advances.
    '''
    from state_manager import _migrate, _migrate_v6_to_v7
    s = {
      'schema_version': 6,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
    }
    out = _migrate_v6_to_v7(dict(s))
    assert 'paper_trades' not in out, (
      'D-08: missing paper_trades key must remain absent after migration'
    )
    out2 = _migrate(dict(s))
    assert out2['schema_version'] == 7

  def test_migrate_v6_to_v7_silent_no_warnings_no_logs(self, caplog) -> None:
    '''D-15 silent migration: migrating 5 rows must emit zero log records and
    must NOT append to state[\'warnings\'] (mirrors Phase 19 silent-migration pattern).
    '''
    import logging
    from state_manager import _migrate_v6_to_v7
    rows = [
      {'id': f'SPI200-2026043{i}-001', 'instrument': 'SPI200',
       'side': 'LONG', 'status': 'open'}
      for i in range(5)
    ]
    s = {
      'schema_version': 6,
      'paper_trades': [dict(r) for r in rows],
      'warnings': [],
    }
    with caplog.at_level(logging.DEBUG):
      out = _migrate_v6_to_v7(dict(s))
    assert len(caplog.records) == 0, (
      f'D-15: silent migration — no log records expected; got {caplog.records!r}'
    )
    assert out.get('warnings') == [], (
      f'D-15: silent migration — warnings must remain empty; got {out["warnings"]!r}'
    )

  def test_full_walk_v0_to_v7_then_load_state(self, tmp_path) -> None:
    '''Write a v0 state (no schema_version) with a paper_trades row missing
    last_alert_state to disk, call load_state, assert schema_version==7 AND
    the pre-seeded paper_trades row carries last_alert_state=None.
    '''
    import json as _json
    path = tmp_path / 'state.json'
    bare_state = {
      # no schema_version → defaults to 0
      'account': INITIAL_ACCOUNT, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {
        'SPI200': {
          'signal': 1, 'signal_as_of': '2026-04-30',
          'as_of_run': '2026-04-30',
        },
        'AUDUSD': {
          'signal': 0, 'signal_as_of': '2026-04-30',
          'as_of_run': '2026-04-30',
        },
      },
      'trade_log': [], 'equity_history': [], 'warnings': [],
      'paper_trades': [
        {'id': 'SPI200-20260430-001', 'instrument': 'SPI200', 'side': 'LONG',
         'status': 'open'},
      ],
    }
    path.write_text(_json.dumps(bare_state, indent=2))
    loaded = load_state(path=path)
    assert loaded['schema_version'] == 7, (
      f'walk-forward chain v0->...->v7 must end at 7; '
      f'got {loaded["schema_version"]}'
    )
    # Phase 20 v6->v7 backfill
    assert loaded['paper_trades'][0]['last_alert_state'] is None, (
      'Phase 20: full walk must stamp last_alert_state=None on paper_trades row'
    )
