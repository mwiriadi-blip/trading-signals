'''Phase 27 Plan 07 — naive-datetime fail-closed regression tests.

Behavior under test:
  - state_manager._assert_tz_aware(dt, *, context) raises ValueError on naive
    datetime (no tzinfo) with the canonical message
    'naive datetime forbidden — must be tz-aware'.
  - tz-aware datetime passes silently.
  - When a write helper that builds an ISO string from a datetime arg
    receives a naive datetime, it raises ValueError BEFORE persisting
    anything (fail-closed at the helper boundary).
  - load_state's UTC-coercion shim accepts a legacy naive ISO timestamp
    in equity_history, emits a DeprecationWarning, and returns a coerced
    state (read-path leniency for old state files).
'''
import json
import warnings as _warnings_mod
from datetime import datetime, timezone

import pytest

import state_manager
from state_manager import (
  _assert_tz_aware,
  load_state,
)


class TestAssertTzAware:
  '''Direct contract tests for the new _assert_tz_aware helper.'''

  def test_assert_tz_aware_rejects_naive(self):
    with pytest.raises(ValueError, match='naive datetime forbidden'):
      _assert_tz_aware(datetime(2026, 1, 1), context='test')

  def test_assert_tz_aware_accepts_aware(self):
    # Must not raise — return value irrelevant; the gate is the side effect.
    _assert_tz_aware(
      datetime(2026, 1, 1, tzinfo=timezone.utc),
      context='test',
    )


class TestSaveStatePathFailClosed:
  '''When a state-write helper takes a datetime arg that flows to .isoformat(),
  the gate must fire at the helper boundary.

  state_manager.append_warning(state, source, message, now=...) is the sole
  helper that takes a datetime arg (`now=`) and converts it via strftime to
  an ISO date string for state persistence. With fail-closed semantics, a
  naive `now` MUST raise ValueError before the FIFO append happens.
  '''

  def test_append_warning_with_naive_now_raises(self):
    state = state_manager.reset_state()
    with pytest.raises(ValueError, match='naive datetime forbidden'):
      state_manager.append_warning(
        state, 'test_source', 'test_message',
        now=datetime(2026, 1, 1),  # naive
      )
    # Verify nothing was appended (fail-closed: write rejected pre-mutation).
    assert state['warnings'] == []

  def test_append_warning_with_aware_now_succeeds(self):
    state = state_manager.reset_state()
    state = state_manager.append_warning(
      state, 'test_source', 'test_message',
      now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert len(state['warnings']) == 1
    assert state['warnings'][0]['source'] == 'test_source'


class TestLoadStateLegacyNaiveISOWarns:
  '''Read-path UTC-coercion shim: legacy state files may have naive ISO
  timestamps in equity_history (older v1.0 builds wrote them). load_state
  must succeed on these but emit DeprecationWarning to nudge re-save.
  '''

  def test_load_state_with_naive_iso_in_legacy_file_warns(self, tmp_path):
    # Build a minimal v11-shaped state with a NAIVE ISO datetime string in
    # equity_history (no tz offset). This simulates a legacy file written
    # before the fail-closed gate landed (schema_version=11 so v11->v12
    # migration runs and moves equity_history into the user bucket, then
    # _coerce_legacy_naive_iso scans the user bucket and emits a warning).
    state_path = tmp_path / 'state.json'
    legacy_state = {
      'schema_version': 11,  # v11 so migration runs and moves equity_history to user bucket
      'account': 100000.0,
      'last_run': None,
      'positions': {'SPI200': None, 'AUDUSD': None},
      # Phase 27 #11 (Plan 27-09): dict shape only at current schema.
      # Inline definition mirrors tests/conftest.py contract (per LEARNING
      # 2026-04-25 Plan 13-02 — testpaths doesn't put tests/ on sys.path).
      'signals': {
        'SPI200': {'signal': 0, 'strategy_version': 'v1.2.0'},
        'AUDUSD': {'signal': 0, 'strategy_version': 'v1.2.0'},
      },
      'trade_log': [],
      'equity_history': [
        # Phase 27 #6: legacy naive ISO timestamp (no offset, no Z).
        {'date': '2026-01-01T00:00:00', 'equity': 100000.0},
      ],
      'warnings': [],
      'initial_account': 100000.0,
      'contracts': {
        'SPI200': state_manager._DEFAULT_SPI_LABEL,
        'AUDUSD': state_manager._DEFAULT_AUDUSD_LABEL,
      },
      'markets': {},
      'strategy_settings': {},
    }
    state_path.write_text(json.dumps(legacy_state))

    # Use catch_warnings to capture (pytest.warns also works; this is more
    # diagnostic on failure).
    with _warnings_mod.catch_warnings(record=True) as caught:
      _warnings_mod.simplefilter('always')
      result = load_state(path=state_path)

    # load_state succeeded — read-path shim coerced rather than rejected.
    # Phase 33 TENANT-01: account now in users bucket
    assert result['users']['u_admin_marc']['account'] == 100000.0
    # At least one DeprecationWarning was emitted mentioning naive ISO.
    deprecation_warnings = [
      w for w in caught
      if issubclass(w.category, DeprecationWarning)
      and 'naive' in str(w.message).lower()
    ]
    assert len(deprecation_warnings) >= 1, (
      f'expected DeprecationWarning about naive ISO; got: {[str(w.message) for w in caught]}'
    )
