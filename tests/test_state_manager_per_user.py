'''Phase 36 TENANT-02 — unit tests for mutate_user_state + load_user_state.

These tests verify the per-user flock wrapper added to state_manager/__init__.py:
  - mutate_user_state acquires state/users/{uid}.lock (OUTER) before delegating
  - lock dir is auto-created (D-03)
  - load_user_state returns the correct state['users'][uid] slice (D-05)
'''
import json
from pathlib import Path

import pytest

from state_manager import load_state, load_user_state, mutate_user_state
from state_manager.migrations import _ADMIN_UID


def _seed_state(path: Path, uid: str) -> dict:
  '''Write a minimal v12-shaped state.json under path for tests.

  contracts must map to known labels from SPI_CONTRACTS / AUDUSD_CONTRACTS so
  load_state can materialise _resolved_contracts without KeyError (line 306).
  '''
  state = {
    'schema_version': 12,
    'admin_user_id': uid,
    'signals': {
      'SPI200': {'last_close': 7820.0, 'last_scalars': {'atr': 50.0}},
      'AUDUSD': {'last_close': 0.652, 'last_scalars': {'atr': 0.005}},
    },
    'markets': {},
    'strategy_settings': {},
    'warnings': [],
    'last_run': '2026-05-14',
    'users': {
      uid: {
        'account': 50_000.0,
        'initial_account': 50_000.0,
        'contracts': {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-mini'},
        'positions': {'SPI200': None, 'AUDUSD': None},
        'trade_log': [],
        'equity_history': [],
        'paper_trades': [],
        'ui_prefs': {'tour_completed': True},
      },
    },
  }
  state_file = path / 'state.json'
  state_file.write_text(json.dumps(state, indent=2))
  return state


class TestMutateUserState:
  '''Unit tests for mutate_user_state flock wrapper (TENANT-02 / D-01..D-03).'''

  def test_mutate_user_state_writes_to_user_bucket(self, tmp_path):
    '''mutate_user_state mutator writes to state["users"][uid]["account"].'''
    uid = _ADMIN_UID
    _seed_state(tmp_path, uid)
    state_file = tmp_path / 'state.json'

    def _set_account(state):
      state['users'][uid]['account'] = 99_999.0

    mutate_user_state(uid, _set_account, path=state_file)
    result = load_state(path=state_file)
    assert result['users'][uid]['account'] == 99_999.0

  def test_mutate_user_state_creates_lock_dir(self, tmp_path, monkeypatch):
    '''mutate_user_state auto-creates state/users/ dir and lock file (D-03).

    monkeypatch.chdir redirects Path("state/users") to tmp_path so lock files
    land in the temp directory rather than the repo state/ dir.
    '''
    uid = _ADMIN_UID
    _seed_state(tmp_path, uid)
    state_file = tmp_path / 'state.json'
    monkeypatch.chdir(tmp_path)

    mutate_user_state(uid, lambda s: None, path=state_file)

    lock_path = tmp_path / 'state' / 'users' / f'{uid}.lock'
    assert lock_path.exists(), f'Expected lock file at {lock_path}'

  def test_load_user_state_returns_user_slice(self, tmp_path):
    '''load_user_state(uid) == load_state(path)["users"][uid].'''
    uid = _ADMIN_UID
    _seed_state(tmp_path, uid)
    state_file = tmp_path / 'state.json'

    user_slice = load_user_state(uid, path=state_file)
    full_state = load_state(path=state_file)

    assert user_slice == full_state['users'][uid]
