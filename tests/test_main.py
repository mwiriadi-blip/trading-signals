'''Phase 4 test suite: orchestrator + CLI + logging bootstrap.

Organized into classes per D-13 (one class per concern dimension):
  TestCLI, TestOrchestrator, TestLoggerConfig.

All tests use tmp_path (pytest built-in) for isolated state files — never
touch the real ./state.json. Clock determinism via the `freezer` fixture
(pytest-freezer 0.4.9, pinned in Wave 0); log-line assertions via pytest's
built-in `caplog` fixture. fetch_ohlcv is monkeypatched at the
`data_fetcher.yf.Ticker` import site (NOT `yfinance.Ticker`) — same idiom
as tests/test_state_manager.py line 228 `patch('state_manager.os.replace', ...)`.

Wave 0 (this commit): empty skeletons with class docstrings. Waves 2-3 fill
in the test methods per the wave annotation in each class docstring
(04-03-PLAN.md + 04-04-PLAN.md).

Wave 2 (04-03-PLAN.md): populates TestOrchestrator (6 methods — DATA-04,
DATA-06, ERR-06, D-12, D-08, AC-1) + TestCLI smoke tests (CLI-04, CLI-05).
AC-1 revision 2026-04-22 lands the headline reversal-ordering regression
test. G-2 revision 2026-04-22 extends the D-08 test to assert on
last_scalars persistence. C-4 revision 2026-04-22 applies the
monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None) strategy
consistently across every main()-invoking caplog-asserting test (see
04-03-PLAN.md <test_strategy>).
'''
import argparse
import json
import logging
import os  # noqa: F401 — used in Wave 3 CLI-01 mtime check
from pathlib import Path

import pandas as pd
import pytest

import data_fetcher  # noqa: F401 — Waves 2/3 monkeypatch target
import main
import state_manager
from data_fetcher import (  # noqa: F401 — Wave 3 ERR-01 raises DataFetchError / ShortFrameError
  DataFetchError,
  ShortFrameError,
)

# =========================================================================
# Module-level path + fixture-dir constants
# =========================================================================

MAIN_PATH = Path('main.py')
TEST_MAIN_PATH = Path('tests/test_main.py')
FETCH_FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'fetch'


# =========================================================================
# Test helpers (Wave 2)
# =========================================================================

def _load_recorded_fixture(name: str) -> pd.DataFrame:
  '''Load a committed fetch fixture (orient='split'). Mirror of
  test_data_fetcher.py's helper; recovers column dtypes identical to a live
  yfinance DataFrame.'''
  path = FETCH_FIXTURE_DIR / name
  return pd.read_json(path, orient='split')


def _seed_fresh_state(state_json: Path) -> dict:
  '''Write a Phase 3 reset_state() to the given path; return the dict.'''
  state = state_manager.reset_state()
  state_manager.save_state(state, path=state_json)
  return state


def _make_args(**overrides) -> argparse.Namespace:
  '''Build an argparse.Namespace matching _build_parser's defaults.'''
  return argparse.Namespace(
    test=overrides.get('test', False),
    reset=overrides.get('reset', False),
    force_email=overrides.get('force_email', False),
    once=overrides.get('once', True),
  )


def _install_fixture_fetch(monkeypatch) -> None:
  '''Monkeypatch main.data_fetcher.fetch_ohlcv to return committed fixtures.'''
  def _fake(sym, **_kw):
    if sym == '^AXJO':
      return _load_recorded_fixture('axjo_400d.json')
    if sym == 'AUDUSD=X':
      return _load_recorded_fixture('audusd_400d.json')
    raise AssertionError(f'unexpected symbol: {sym!r}')
  monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', _fake)


# =========================================================================
# Test classes — one per concern dimension (D-13)
# =========================================================================

class TestCLI:
  '''CLI-01 .. CLI-05: argparse dispatch + flag-combo validation.

  Wave 3 fills CLI-01/02/03 (04-04-PLAN.md). Wave 2 adds the --once + default
  smoke tests (CLI-04, CLI-05).
  '''

  def test_once_flag_runs_single_check(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''CLI-04: `main.main(['--once'])` returns 0, emits the [Sched] One-shot
    mode log line, and calls fetch exactly twice (SPI200 + AUDUSD).
    '''
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    # C-4 revision: keep pytest's caplog handler attached by no-op-ing basicConfig.
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    _seed_fresh_state(tmp_path / 'state.json')

    fetch_calls: list[str] = []

    def _tracking_fetch(sym, **_kw):
      fetch_calls.append(sym)
      if sym == '^AXJO':
        return _load_recorded_fixture('axjo_400d.json')
      return _load_recorded_fixture('audusd_400d.json')
    monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', _tracking_fetch)

    rc = main.main(['--once'])
    assert rc == 0
    assert len(fetch_calls) == 2, (
      f'CLI-04: expected exactly 2 fetch calls (one per symbol), got {fetch_calls}'
    )
    assert '[Sched] One-shot mode (scheduler wiring lands in Phase 7)' in caplog.text, (
      'CLI-04: D-07 one-shot log line missing from caplog.text'
    )

  def test_default_mode_runs_once_and_logs_schedule_stub(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''CLI-05 / D-07: default `main.main([])` behaves identically to --once in
    Phase 4 (scheduler wiring lands in Phase 7).
    '''
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    rc = main.main([])
    assert rc == 0
    assert '[Sched] One-shot mode (scheduler wiring lands in Phase 7)' in caplog.text, (
      'CLI-05: D-07 one-shot log line missing from default-mode caplog.text'
    )


class TestOrchestrator:
  '''D-11 9-step sequence + DATA-04/05/06 + ERR-01/06 + D-08 upgrade +
  D-12 translator + AC-1 reversal-ordering (2026-04-22 revision — see
  04-03-PLAN.md).

  Uses pytest-freezer `freezer` fixture for run_date determinism and
  `caplog` for [Prefix] log assertions. Waves 2-3 fill this in.
  '''

  def test_short_frame_raises_and_no_state_written(
      self, tmp_path, monkeypatch) -> None:
    '''DATA-04 / D-03 + Pitfall 6: short-frame (< 300 rows) raises
    ShortFrameError IMMEDIATELY after fetch (before compute_indicators) with
    no state.json mutation.
    '''
    monkeypatch.chdir(tmp_path)  # state-path isolation lock (Phase 3 precedent)
    state_json = tmp_path / 'state.json'
    _seed_fresh_state(state_json)
    mtime_before = state_json.stat().st_mtime_ns

    idx = pd.date_range('2024-01-01', periods=299, freq='B')
    short_df = pd.DataFrame(
      {c: list(range(299)) for c in ['Open', 'High', 'Low', 'Close', 'Volume']},
      index=idx,
    )
    monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', lambda sym, **kw: short_df)

    with pytest.raises(ShortFrameError, match='need >= 300'):
      main.run_daily_check(_make_args(once=True))

    mtime_after = state_json.stat().st_mtime_ns
    assert mtime_before == mtime_after, (
      'DATA-04: state.json must NOT be written when fetch returns a short frame'
    )

  @pytest.mark.freeze_time('2026-04-21 09:00:03+08:00')
  def test_signal_as_of_and_run_date_logged_separately(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''DATA-06 / D-13: signal_as_of (from df.index[-1]) and run_date
    (AWST wall-clock) are BOTH logged on every run, separately.
    '''
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    rc = main.main(['--test'])
    assert rc == 0

    # D-13: signal_as_of is the last-bar ISO date — the axjo fixture's last
    # bar is 2026-04-19, audusd's is 2026-04-20.
    assert 'signal_as_of=2026-04-19' in caplog.text, (
      'DATA-06: axjo signal_as_of line missing (expected 2026-04-19)'
    )
    assert 'signal_as_of=2026-04-20' in caplog.text, (
      'DATA-06: audusd signal_as_of line missing (expected 2026-04-20)'
    )
    # D-13: run_date is AWST wall-clock — frozen at 2026-04-21 09:00:03.
    assert 'Run 2026-04-21 09:00:03 AWST' in caplog.text, (
      'DATA-06: run_date line (AWST wall-clock) missing'
    )

  @pytest.mark.freeze_time('2026-04-21 09:00:03+08:00')
  def test_log_format_matches_d14_contract(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''ERR-06 / D-14: per-instrument log block emits [Fetch] / [Signal] /
    [State] / [Sched] prefixes in the exact shape from 04-RESEARCH §Example 4.
    '''
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    rc = main.main(['--once'])
    assert rc == 0

    text = caplog.text
    # D-14 shape: [Fetch] <symbol> ok: <N> bars, last_bar=<ISO>, fetched_in=<X.Xs>
    assert '[Fetch] ^AXJO ok:' in text
    assert '[Fetch] AUDUSD=X ok:' in text
    assert 'last_bar=2026-04-19' in text
    # D-14 shape: [Signal] <symbol> signal=<...> signal_as_of=<ISO> (ADX=..., moms=..., rvol=...)
    assert '[Signal] ^AXJO signal=' in text
    assert '[Signal] AUDUSD=X signal=' in text
    assert 'ADX=' in text
    assert 'rvol=' in text
    # D-14 shape: [State] <symbol> position OR no position, plus trade-closed line.
    assert '[State] ^AXJO' in text
    assert '[State] AUDUSD=X' in text
    # D-14 footer: [Sched] Run <...> AWST done in <...>
    assert '[Sched] Run' in text and 'AWST done in' in text

  def test_closed_trade_to_record_gross_pnl_is_raw_price_delta(self) -> None:
    '''D-12 / Pitfall 8: `_closed_trade_to_record` recomputes gross_pnl from
    price-delta; it MUST NOT assign `ct.realised_pnl` to `gross_pnl` (which
    already has the closing-half cost deducted).

    LONG example: 2 contracts, entry 8000, exit 8050, mult 5
      expected gross_pnl = +1 * (8050 - 8000) * 2 * 5 = 500.0
      ct.realised_pnl = 500 - (6 * 2 / 2) = 494.0   # Phase 2 close-half deducted
    '''
    from sizing_engine import ClosedTrade
    ct = ClosedTrade(
      direction='LONG', entry_price=8000.0, exit_price=8050.0,
      n_contracts=2, realised_pnl=494.0, exit_reason='flat_signal',
    )
    rec = main._closed_trade_to_record(
      ct, symbol='SPI200', multiplier=5.0, cost_aud=6.0,
      entry_date='2026-04-10', run_date_iso='2026-04-21',
    )
    assert rec['gross_pnl'] == pytest.approx(500.0)
    # Distractor: if implementer copies ct.realised_pnl, this fails.
    assert rec['gross_pnl'] != ct.realised_pnl, (
      'Pitfall 8: gross_pnl must NOT equal ct.realised_pnl '
      '(closing-half cost would double-count)'
    )
    # All 11 required fields populated.
    required = {
      'instrument', 'direction', 'entry_date', 'exit_date',
      'entry_price', 'exit_price', 'gross_pnl', 'n_contracts',
      'exit_reason', 'multiplier', 'cost_aud',
    }
    assert required.issubset(rec.keys())
    assert rec['instrument'] == 'SPI200'
    assert rec['entry_date'] == '2026-04-10'
    assert rec['exit_date'] == '2026-04-21'
    assert rec['multiplier'] == 5.0
    assert rec['cost_aud'] == 6.0

    # SHORT mirror: direction_mult == -1.
    ct_short = ClosedTrade(
      direction='SHORT', entry_price=8050.0, exit_price=8000.0,
      n_contracts=3, realised_pnl=742.5, exit_reason='signal_reversal',
    )
    rec_short = main._closed_trade_to_record(
      ct_short, symbol='SPI200', multiplier=5.0, cost_aud=6.0,
      entry_date='2026-04-10', run_date_iso='2026-04-21',
    )
    # -1 * (8000 - 8050) * 3 * 5 = 750.0
    assert rec_short['gross_pnl'] == pytest.approx(750.0)

  def test_orchestrator_reads_both_int_and_dict_signal_shape(
      self, tmp_path, monkeypatch) -> None:
    '''D-08 / Pitfall 7 + G-2 revision 2026-04-22: orchestrator reads int-shape
    AND dict-shape signals, always writes dict shape post-run INCLUDING
    last_scalars (G-2 — Phase 5/6 need these to render ADX/Mom/RVol without
    re-fetching).
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    state_json = tmp_path / 'state.json'
    seed = state_manager.reset_state()
    seed['signals']['SPI200'] = 0  # Phase 3 int shape
    # Phase 4 pre-G-2 dict shape (no last_scalars).
    seed['signals']['AUDUSD'] = {
      'signal': 0, 'signal_as_of': '2026-04-10', 'as_of_run': '2026-04-10',
    }
    state_manager.save_state(seed, path=state_json)
    _install_fixture_fetch(monkeypatch)

    rc = main.main(['--once'])
    assert rc == 0

    post = json.loads(state_json.read_text())
    for key in ('SPI200', 'AUDUSD'):
      sig = post['signals'][key]
      assert isinstance(sig, dict), (
        f'{key}: expected dict (D-08 always-write), got {type(sig).__name__}'
      )
      assert 'signal' in sig
      assert 'signal_as_of' in sig
      assert 'as_of_run' in sig
      # G-2 revision 2026-04-22: last_scalars persisted for Phase 5/6.
      assert 'last_scalars' in sig, (
        f'{key}: G-2 revision — last_scalars missing from signals dict'
      )
      assert isinstance(sig['last_scalars'], dict)
      # Sanity: real scalars dict from signal_engine.get_latest_indicators.
      assert 'adx' in sig['last_scalars']
      assert 'rvol' in sig['last_scalars']

  def test_reversal_long_to_short_preserves_new_position(
      self, tmp_path, monkeypatch) -> None:
    '''AC-1 revision 2026-04-22 — headline regression guard.

    On a LONG→SHORT signal reversal, `state['positions']['SPI200']` must be a
    SHORT Position post-run — NOT None. Proves run_daily_check calls
    record_trade BEFORE assigning result.position_after. If the ordering is
    reversed (old-bug), record_trade wipes state['positions']['SPI200'] to
    None AFTER position_after was assigned, and this test fails with
    `state['positions']['SPI200'] is None`.
    '''
    from sizing_engine import ClosedTrade, StepResult

    monkeypatch.chdir(tmp_path)
    state_json = tmp_path / 'state.json'
    # Seed: LONG on SPI200 (open since 2026-04-10); FLAT on AUDUSD.
    seed = state_manager.reset_state()
    seed['positions']['SPI200'] = {
      'direction': 'LONG',
      'entry_price': 8000.0,
      'entry_date': '2026-04-10',
      'n_contracts': 2,
      'pyramid_level': 0,
      'peak_price': 8100.0,
      'trough_price': None,
      'atr_entry': 50.0,
    }
    seed['signals']['SPI200'] = {
      'signal': 1, 'signal_as_of': '2026-04-10', 'as_of_run': '2026-04-10',
      'last_scalars': {},
    }
    seed['signals']['AUDUSD'] = 0
    state_manager.save_state(seed, path=state_json)

    _install_fixture_fetch(monkeypatch)

    # Force LONG→SHORT reversal for SPI200 (first call); FLAT for AUDUSD (second).
    def fake_get_signal(_df):
      fake_get_signal.calls += 1
      return -1 if fake_get_signal.calls == 1 else 0
    fake_get_signal.calls = 0
    monkeypatch.setattr(main.signal_engine, 'get_signal', fake_get_signal)

    short_position = {
      'direction': 'SHORT',
      'entry_price': 8050.0,
      'entry_date': '2026-04-21',
      'n_contracts': 3,
      'pyramid_level': 0,
      'peak_price': None,
      'trough_price': 8050.0,
      'atr_entry': 50.0,
    }
    closed_long = ClosedTrade(
      direction='LONG', entry_price=8000.0, exit_price=8050.0,
      n_contracts=2, realised_pnl=494.0, exit_reason='signal_reversal',
    )

    def fake_step(position, bar, indicators, old_signal, new_signal,
                   account, multiplier, cost_aud_open):
      fake_step.calls += 1
      if fake_step.calls == 1:
        # SPI200 — reversal: close LONG, open SHORT.
        return StepResult(
          position_after=short_position,
          closed_trade=closed_long,
          sizing_decision=None,
          pyramid_decision=None,
          unrealised_pnl=0.0,
          warnings=[],
        )
      # AUDUSD — no-op FLAT.
      return StepResult(
        position_after=None, closed_trade=None, sizing_decision=None,
        pyramid_decision=None, unrealised_pnl=0.0, warnings=[],
      )
    fake_step.calls = 0
    monkeypatch.setattr(main.sizing_engine, 'step', fake_step)

    rc = main.run_daily_check(_make_args(once=True))
    assert rc == 0

    post = json.loads(state_json.read_text())
    sp = post['positions']['SPI200']
    assert sp is not None, (
      'AC-1 revision: state[positions][SPI200] is None — the new SHORT '
      'reversal position was wiped by record_trade. Check run_daily_check '
      'mutation ORDERING: record_trade must be called BEFORE '
      "state[positions][state_key] = result.position_after."
    )
    assert sp['direction'] == 'SHORT', (
      f'AC-1 revision: expected SHORT after reversal, got {sp!r}'
    )
    assert sp['n_contracts'] == 3
    assert sp['entry_price'] == 8050.0
    # Trade log contains the closed LONG with the right metadata.
    assert len(post['trade_log']) == 1, (
      f'AC-1: expected 1 closed trade, got {len(post["trade_log"])}'
    )
    tl = post['trade_log'][0]
    assert tl['direction'] == 'LONG'
    assert tl['exit_reason'] == 'signal_reversal'
    assert tl['instrument'] == 'SPI200'
    # entry_date_pre_close capture: original 2026-04-10, not run_date.
    assert tl['entry_date'] == '2026-04-10'


class TestLoggerConfig:
  '''Pitfall 4: main() configures logging via basicConfig(force=True).

  Wave 0 scaffolds; Wave 3 fills body (04-04-PLAN.md).
  '''
