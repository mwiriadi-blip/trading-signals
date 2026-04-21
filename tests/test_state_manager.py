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
from datetime import datetime, timezone  # noqa: F401 — used in Wave 1/2 clock injection
from pathlib import Path
from unittest.mock import patch  # noqa: F401 — used in Wave 1 TestAtomicity

import pytest  # noqa: F401 — used across Waves 1/2/3 for raises / parametrize

from state_manager import (
  MIGRATIONS,  # noqa: F401 — used in Wave 1 TestSchemaVersion
  append_warning,  # noqa: F401 — used in Wave 2 TestWarnings
  load_state,  # noqa: F401 — used in Waves 1/2 TestLoadSave/TestCorruptionRecovery
  record_trade,  # noqa: F401 — used in Wave 3 TestRecordTrade
  reset_state,  # noqa: F401 — used in Wave 2 TestReset
  save_state,  # noqa: F401 — used in Wave 1 TestLoadSave/TestAtomicity
  update_equity_history,  # noqa: F401 — used in Wave 3 TestEquityHistory
)
from system_params import (
  INITIAL_ACCOUNT,  # noqa: F401 — used in Wave 2 TestReset
  MAX_WARNINGS,  # noqa: F401 — used in Wave 2 TestWarnings
  STATE_FILE,  # noqa: F401 — used in Wave 1 TestLoadSave default path
  STATE_SCHEMA_VERSION,  # noqa: F401 — used in Wave 1 TestSchemaVersion
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
    }
    save_state(state, path=path)
    loaded = load_state(path=path)
    assert loaded == state, 'round-trip must preserve every field including nested dicts/lists'

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
  pass

class TestRecordTrade:
  '''STATE-05 / D-13..D-16 / D-19 / D-20: validation, closing-half cost,
  account mutation, position close, no-mutation contract.

  All arithmetic verified from first principles (no oracle files needed).
  CRITICAL: gross_pnl is RAW price-delta P&L per D-14, NOT realised_pnl.
  Wave 3 fills this in.
  '''
  pass

class TestEquityHistory:
  '''STATE-06 / D-04 / B-4: update_equity_history appends {date, equity}
  after boundary validation (date shape + equity finiteness).

  Wave 3 fills this in.
  '''
  pass

class TestReset:
  '''STATE-07 / D-01 / D-03: reset_state shape — $100k account, None positions,
  FLAT signals, empty collections.

  Wave 2 fills this in.
  '''
  pass

class TestWarnings:
  '''D-09 / D-10 / D-11 / B-5: warning shape, AWST date, FIFO bound to MAX_WARNINGS.

  Wave 2 fills this in.
  '''
  pass

class TestSchemaVersion:
  '''STATE-04: MIGRATIONS dict walk-forward; no-op at v1; handles missing key.

  Wave 1 fills this in.
  '''

  def test_migrations_dict_has_v1_no_op(self) -> None:
    '''STATE-04: MIGRATIONS[1] is the identity (no-op) per CONTEXT.md.'''
    sample = {'x': 1, 'y': 'two'}
    assert MIGRATIONS[1](sample) == sample, 'v1 migration must be identity (no-op hook)'

  def test_schema_v1_no_op_migration(self, tmp_path) -> None:
    '''STATE-04: a v1 state on disk loads with schema_version unchanged and all fields preserved.'''
    path = tmp_path / 'state.json'
    state = {
      'schema_version': STATE_SCHEMA_VERSION,
      'account': INITIAL_ACCOUNT,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      'signals': {'SPI200': 0, 'AUDUSD': 0},
      'trade_log': [], 'equity_history': [], 'warnings': [],
    }
    save_state(state, path=path)
    loaded = load_state(path=path)
    assert loaded['schema_version'] == STATE_SCHEMA_VERSION
    assert loaded == state, 'v1 no-op migration must not mutate any field'

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
