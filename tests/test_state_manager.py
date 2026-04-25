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
    '''STATE-04 (Phase 8 extension): after _migrate, schema_version equals
    STATE_SCHEMA_VERSION (now 2 per Phase 8).'''
    state = {
      # no schema_version → defaults to 0
      'account': INITIAL_ACCOUNT, 'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    migrated = _migrate(state)
    assert migrated['schema_version'] == STATE_SCHEMA_VERSION
    assert STATE_SCHEMA_VERSION == 2, 'Phase 8 bumps STATE_SCHEMA_VERSION to 2'


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


# =========================================================================
# Phase 14 D-13 — fcntl exclusive lock around _atomic_write
# =========================================================================

class TestFcntlLock:
  '''Phase 14 D-13: cross-process state.json coordination via fcntl.LOCK_EX.
  Plan 14-02 implements; this skeleton lets Wave 1 fixtures land predictably.

  Test surface (Plan 14-02):
    - Single-process happy path: fcntl.flock acquired + released around
      the existing tempfile->fsync->replace->dir-fsync sequence.
    - Multiprocess contention: a child process holding LOCK_EX for ~0.5s
      causes the main process save_state to block >= 0.4s and < 1.0s
      (RESEARCH §Pattern 9 line 743).
    - Lock release on exception: if _atomic_write raises mid-write, the
      finally clause must still call fcntl.LOCK_UN + close(lock_fd).
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-02 implements')


# =========================================================================
# Phase 14 D-09 — schema migration v2 -> v3 (Position.manual_stop backfill)
# =========================================================================

class TestSchemaMigrationV2ToV3:
  '''Phase 14 D-09: _migrate_v2_to_v3 backfills manual_stop=None on every
  non-None Position dict in state['positions']. Plan 14-02 implements.

  Round-trip discipline (RESEARCH §Pattern 11):
    load(v2 fixture) -> assert manual_stop is None on each position
      -> save_state -> re-load -> assert schema_version == 3 +
      manual_stop preserved.

  Fixture: tests/fixtures/state_v2_no_manual_stop.json (created in
  Plan 14-01) — schema_version=2 with two open positions and NO
  manual_stop key.
  '''

  def test_placeholder_wave_0(self):
    pytest.skip('Wave 0 skeleton; Plan 14-02 implements')
