'''Phase 27 Plan 27-10 Task 2 — run-date logging assertion.

Locks in the invariant that every daily run logs the AWST run-date at
INFO level in the canonical `[Daily] run-date YYYY-MM-DD` shape so
operators tailing systemd journalctl can grep for daily runs without
needing to reverse-engineer an alternative log format.

Verified via pytest's caplog fixture (no log-format coupling — only
record-level + message-text).
'''
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
import pytest

import data_fetcher  # noqa: F401 — monkeypatch target
import main
import state_manager


FETCH_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'fetch'


def _load_recorded_fixture(name: str) -> pd.DataFrame:
  return pd.read_json(FETCH_FIXTURE_DIR / name, orient='split')


def _seed_fresh_state(state_json: Path) -> dict:
  state = state_manager.reset_state()
  state_manager.save_state(state, path=state_json)
  return state


def _install_fixture_fetch(monkeypatch) -> None:
  def _fake(sym, **_kw):
    if sym == '^AXJO':
      return _load_recorded_fixture('axjo_400d.json')
    if sym == 'AUDUSD=X':
      return _load_recorded_fixture('audusd_400d.json')
    raise AssertionError(f'unexpected symbol: {sym!r}')
  monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', _fake)


class TestRunDateLogging:
  '''Phase 27 Plan 27-10 Task 2 — every daily run logs the AWST run-date
  at INFO level in the canonical `[Daily] run-date YYYY-MM-DD` shape.'''

  @pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')  # Mon 08:00 AWST
  def test_daily_run_logs_run_date(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''Invoke main(['--once']) on stub state; capture caplog at INFO; assert
    at least one record matches the canonical r'\\[Daily\\] run-date \\d{4}-\\d{2}-\\d{2}'
    pattern. freeze_time pins Mon so the weekday gate doesn't short-circuit.'''
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    rc = main.main(['--once'])
    assert rc == 0

    pattern = re.compile(r'\[Daily\] run-date \d{4}-\d{2}-\d{2}')
    matches = [
      record for record in caplog.records
      if record.levelno == logging.INFO and pattern.search(record.getMessage())
    ]
    assert matches, (
      "Phase 27 Plan 27-10 Task 2: expected at least one INFO-level log "
      "record matching r'\\[Daily\\] run-date \\d{4}-\\d{2}-\\d{2}' from "
      f"main.run_daily_check; got {len(caplog.records)} INFO records, "
      f"first 5 messages: {[r.getMessage() for r in caplog.records[:5]]}"
    )
