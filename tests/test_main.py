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
import math
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

  @pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')  # Mon 08:00 AWST
  def test_once_flag_runs_single_check(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''CLI-04 / Phase 7: `main.main(['--once'])` returns 0, calls fetch
    exactly twice (SPI200 + AUDUSD), and does NOT enter the schedule loop.

    Phase 7 D-05: deprecated `[Sched] One-shot mode` log line is gone from
    run_daily_check. --once also does NOT enter the schedule loop, so the
    new `[Sched] scheduler entered` log line also does NOT fire (CLI-04
    contract: --once stays one-shot).

    freeze_time pins Mon so the weekday gate doesn't short-circuit.
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
    # Phase 7 D-05: deprecated `[Sched] One-shot mode` log line deleted from
    # run_daily_check. --once does NOT enter the schedule loop, so the NEW
    # `[Sched] scheduler entered` line ALSO does NOT fire (CLI-04 contract:
    # --once stays one-shot).
    assert '[Sched] scheduler entered' not in caplog.text, (
      'CLI-04: --once must NOT enter the schedule loop'
    )
    assert 'One-shot mode (scheduler wiring lands in Phase 7)' not in caplog.text, (
      'Phase 7 D-05: Phase 4 stub log line must be deleted from run_daily_check'
    )

  def test_default_mode_enters_schedule_loop(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''Phase 7 D-05 / CLI-05: default `main.main([])` runs an immediate first
    check then enters the schedule loop.

    Injects fakes for _run_daily_check_caught AND _run_schedule_loop so the
    test doesn't hang in the infinite loop. Records call order to verify
    D-04 (immediate first run BEFORE loop entry).

    07-REVIEWS.md Codex MEDIUM-fix: patches `main._get_process_tzname` (the
    Wave 0 wrapper) rather than `time.tzname` directly. The fake loop never
    actually checks the tzname (it's a no-op), but patching the wrapper
    keeps the test defensive if someone later removes the fake.
    '''
    monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    call_order: list[tuple[str, str]] = []
    monkeypatch.setattr(
      main, '_run_daily_check_caught',
      lambda job, args: call_order.append(('caught', job.__name__)),
    )

    def _fake_loop(job, args):
      call_order.append(('loop', job.__name__))
      return 0

    monkeypatch.setattr(main, '_run_schedule_loop', _fake_loop)

    rc = main.main([])
    assert rc == 0
    assert call_order == [
      ('caught', 'run_daily_check'),
      ('loop', 'run_daily_check'),
    ], 'D-04: immediate first-run must precede loop entry'
    assert 'One-shot mode (scheduler wiring lands in Phase 7)' not in caplog.text, (
      'Phase 7 D-05: Phase 4 stub log line must be deleted from run_daily_check'
    )

  # -----------------------------------------------------------------------
  # Wave 3: CLI-01 / CLI-02 / CLI-03 (04-04-PLAN.md)
  # -----------------------------------------------------------------------

  def test_test_flag_leaves_state_json_mtime_unchanged(
      self, tmp_path, monkeypatch) -> None:
    '''CLI-01: --test must NOT mutate state.json (structural read-only proof).

    Records st_mtime_ns before and after main.main(['--test']); asserts
    equality. The Wave 2 run_daily_check step 8 guard (if args.test: return
    before save_state) makes this structural, not behavioural.
    '''
    monkeypatch.chdir(tmp_path)
    # C-4 revision: keep pytest's caplog handler attached by no-op-ing basicConfig.
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    state_json = tmp_path / 'state.json'
    _seed_fresh_state(state_json)
    mtime_before = state_json.stat().st_mtime_ns
    _install_fixture_fetch(monkeypatch)

    rc = main.main(['--test'])
    mtime_after = state_json.stat().st_mtime_ns
    assert rc == 0
    assert mtime_before == mtime_after, (
      'CLI-01: --test must NOT mutate state.json'
    )

  def test_reset_with_confirmation_writes_fresh_state(
      self, tmp_path, monkeypatch) -> None:
    '''CLI-02 happy path: --reset with RESET_CONFIRM=YES (env bypass) reinits
    state.json to the reset_state() baseline ($100k, empty trade_log).

    Phase 8 update: pass explicit --initial-account / --spi-contract /
    --audusd-contract flags (D-13 non-TTY guard requires this).
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    # Seed a non-default state — account != INITIAL, with a fake trade.
    state = state_manager.reset_state()
    state['account'] = 42_000.0
    state['trade_log'] = [{'fake': 'trade'}]
    state_manager.save_state(state, path=tmp_path / 'state.json')
    monkeypatch.setenv('RESET_CONFIRM', 'YES')

    rc = main.main([
      '--reset',
      '--initial-account', '100000',
      '--spi-contract', 'spi-mini',
      '--audusd-contract', 'audusd-standard',
    ])
    assert rc == 0

    from system_params import INITIAL_ACCOUNT
    post = json.loads((tmp_path / 'state.json').read_text())
    assert post['account'] == INITIAL_ACCOUNT, (
      f'CLI-02: post-reset account should be ${INITIAL_ACCOUNT}, got {post["account"]}'
    )
    assert post['trade_log'] == [], (
      'CLI-02: post-reset trade_log should be empty'
    )

  def test_reset_without_confirmation_does_not_write(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''CLI-02 cancel path: --reset with confirm != 'YES' does NOT mutate
    state.json and returns exit code 1 (operator cancellation, distinct
    from argparse=2 and success=0).

    Phase 8 update: supply the three CONF flags explicitly so the Q&A
    short-circuits to the YES prompt, which we reject with 'no'. The
    interactive path's own 'q' quit works similarly but this keeps the
    existing assertion intent (confirm step rejection).
    '''
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    monkeypatch.setattr('main._stdin_isatty', lambda: True)
    state_json = tmp_path / 'state.json'
    _seed_fresh_state(state_json)
    mtime_before = state_json.stat().st_mtime_ns
    # Simulate operator typing 'no' at the YES prompt.
    monkeypatch.setattr('builtins.input', lambda prompt='': 'no')

    rc = main.main([
      '--reset',
      '--initial-account', '100000',
      '--spi-contract', 'spi-mini',
      '--audusd-contract', 'audusd-standard',
    ])
    assert rc == 1, (
      'CLI-02 cancel: expected exit code 1 (operator cancel), got '
      f'{rc} — must not be 0 (success) or 2 (argparse error).'
    )
    assert state_json.stat().st_mtime_ns == mtime_before, (
      'CLI-02 cancel: state.json mtime must be unchanged after cancellation'
    )
    assert '--reset cancelled by operator' in caplog.text, (
      'CLI-02 cancel: expected [State] --reset cancelled by operator log line'
    )

  # -----------------------------------------------------------------------
  # Phase 6 Wave 2 (06-03): CLI-03 real dispatch + CLI-01 email-on-test.
  # Replaces the Phase 4 `test_force_email_logs_stub_and_exits_zero` test.
  # -----------------------------------------------------------------------

  def test_force_email_sends_live_email(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''CLI-03 Phase 6: --force-email invokes notifier.send_daily_email
    with post-run state + run_date. Phase 4 stub is replaced.

    Phase 8 D-08 update: fake_send returns SendStatus instead of int 0.
    '''
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    sent: list[tuple] = []

    import notifier

    def _fake_send(state, old_signals, run_date, is_test=False):
      sent.append((state, old_signals, run_date, is_test))
      return notifier.SendStatus(ok=True, reason=None)

    monkeypatch.setattr(notifier, 'send_daily_email', _fake_send)

    rc = main.main(['--force-email'])
    assert rc == 0, '--force-email must exit 0 on success'
    assert len(sent) == 1, '--force-email must invoke send_daily_email exactly once'
    _state, _old_signals, _run_date, is_test = sent[0]
    assert is_test is False, '--force-email alone must pass is_test=False'

  def test_force_email_captures_post_run_state(
      self, tmp_path, monkeypatch) -> None:
    '''D-05 capture: the state passed to send_daily_email is post-compute
    (dict-shape signals with last_scalars + last_close), proving the dispatch
    happens AFTER run_daily_check mutates state['signals'].

    Phase 8 D-08 update: fake_send returns SendStatus.
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    captured: list[dict] = []

    import notifier

    def _fake_send(state, old_signals, run_date, is_test=False):
      captured.append(state)
      return notifier.SendStatus(ok=True, reason=None)

    monkeypatch.setattr(notifier, 'send_daily_email', _fake_send)

    rc = main.main(['--force-email'])
    assert rc == 0
    assert len(captured) == 1
    state = captured[0]
    # Post-compute D-08 dict shape: last_scalars + last_close present.
    sig = state['signals']['SPI200']
    assert isinstance(sig, dict), (
      f'D-05: expected post-compute dict shape; got {type(sig).__name__}'
    )
    assert 'last_scalars' in sig and 'last_close' in sig, (
      'D-05: state passed to email must be post-compute (G-2 + B-1 fields present)'
    )

  def test_test_flag_sends_test_prefixed_email_no_state_mutation(
      self, tmp_path, monkeypatch) -> None:
    '''CLI-01 Phase 6: --test sends [TEST] email AND state.json mtime unchanged.

    Phase 8 D-08 update: fake_send returns SendStatus.
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    state_json = tmp_path / 'state.json'
    _seed_fresh_state(state_json)
    mtime_before = state_json.stat().st_mtime_ns
    _install_fixture_fetch(monkeypatch)

    sent: list[bool] = []

    import notifier

    def _fake_send(state, old_signals, run_date, is_test=False):
      sent.append(is_test)
      return notifier.SendStatus(ok=True, reason=None)

    monkeypatch.setattr(notifier, 'send_daily_email', _fake_send)

    rc = main.main(['--test'])
    mtime_after = state_json.stat().st_mtime_ns
    assert rc == 0
    assert mtime_before == mtime_after, (
      'CLI-01: --test must NOT mutate state.json'
    )
    assert sent == [True], '--test must call send_daily_email with is_test=True'

  def test_force_email_and_test_combined(
      self, tmp_path, monkeypatch) -> None:
    '''D-05 + D-15: --force-email --test runs compute-then-email with is_test=True
    AND does NOT persist state (CLI-01 structural lock preserved).

    Phase 8 D-08 update: fake_send returns SendStatus.
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    state_json = tmp_path / 'state.json'
    _seed_fresh_state(state_json)
    mtime_before = state_json.stat().st_mtime_ns
    _install_fixture_fetch(monkeypatch)

    sent: list[bool] = []

    import notifier

    def _fake_send(state, old_signals, run_date, is_test=False):
      sent.append(is_test)
      return notifier.SendStatus(ok=True, reason=None)

    monkeypatch.setattr(notifier, 'send_daily_email', _fake_send)

    rc = main.main(['--force-email', '--test'])
    assert rc == 0
    assert sent == [True]
    assert state_json.stat().st_mtime_ns == mtime_before, (
      'CLI-01: --force-email --test must NOT mutate state.json'
    )

  def test_default_mode_does_NOT_send_email(
      self, tmp_path, monkeypatch) -> None:
    '''CLI-05 default / CLI-04 --once: no email dispatch — only --force-email
    or --test trigger the email per D-15.

    Phase 7 update: default mode now enters the schedule loop. Stub out
    _run_schedule_loop so the test doesn't hang, and patch
    main._get_process_tzname per 07-REVIEWS.md Codex MEDIUM-fix (defense
    in-depth; fake loop is a no-op but wrapper patch keeps test portable).
    '''
    monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)
    # Phase 7: stub the schedule loop so test doesn't hang.
    monkeypatch.setattr(main, '_run_schedule_loop', lambda job, args: 0)

    sent: list[int] = []

    def _fail_if_called(*a, **kw):
      sent.append(1)
      raise AssertionError('default mode must NOT invoke send_daily_email')

    import notifier
    monkeypatch.setattr(notifier, 'send_daily_email', _fail_if_called)

    rc = main.main([])
    assert rc == 0
    assert sent == [], 'default mode must NOT invoke send_daily_email'

  def test_once_mode_does_NOT_send_email(
      self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    sent: list[int] = []

    def _fail_if_called(*a, **kw):
      sent.append(1)
      raise AssertionError('--once must NOT invoke send_daily_email')

    import notifier
    monkeypatch.setattr(notifier, 'send_daily_email', _fail_if_called)

    rc = main.main(['--once'])
    assert rc == 0
    assert sent == []


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
      # B-1 revision 2026-04-22 (Phase 5 Wave 0): last_close persisted for
      # UI-SPEC §Positions table Current-price column.
      assert 'last_close' in sig, (
        f'{key}: B-1 revision — last_close missing from signals dict'
      )
      assert isinstance(sig['last_close'], float), (
        f'{key}: last_close must be float, got {type(sig["last_close"]).__name__}'
      )
      assert math.isfinite(sig['last_close']), (
        f'{key}: last_close must be finite, got {sig["last_close"]!r}'
      )
      assert sig['last_close'] > 0, (
        f'{key}: last_close should be positive (fixture fetches produce realistic prices)'
      )

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

    # Phase 6 D-05 refactor: run_daily_check now returns 4-tuple.
    rc, _state, _old_signals, _run_date = main.run_daily_check(_make_args(once=True))
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

  # -----------------------------------------------------------------------
  # Wave 3: DATA-05 stale-bar + ERR-01 fetch failure exit mapping
  # -----------------------------------------------------------------------

  @pytest.mark.freeze_time('2026-04-21 09:00:03+08:00')
  def test_stale_bar_appends_warning(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''DATA-05 / D-09: 6d-stale last bar logs [Fetch] WARN and appends
    ('fetch', <message>) to pending_warnings which the Wave 2 flush loop
    persists to state['warnings'] via state_manager.append_warning.

    Frozen clock: 2026-04-21 AWST.
    Hand-built fixture: last bar 2026-04-15 (business days back ~6 days).
    Threshold: _STALE_THRESHOLD_DAYS = 3.
    '''
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    state_manager.save_state(
      state_manager.reset_state(), path=tmp_path / 'state.json',
    )
    # 400 rows of synthetic OHLCV ending 2026-04-15 (6 days before frozen
    # run_date 2026-04-21). Passes DATA-04 300-row floor.
    idx = pd.date_range(end='2026-04-15', periods=400, freq='B')
    fake_df = pd.DataFrame(
      {c: [100.0 + i for i in range(400)]
       for c in ['Open', 'High', 'Low', 'Close', 'Volume']},
      index=idx,
    )
    monkeypatch.setattr(
      main.data_fetcher, 'fetch_ohlcv', lambda sym, **kw: fake_df,
    )

    rc = main.main(['--once'])
    assert rc == 0

    post = json.loads((tmp_path / 'state.json').read_text())
    assert len(post['warnings']) >= 1, (
      'DATA-05: expected at least one queued warning after stale-bar detection'
    )
    stale_warnings = [
      w for w in post['warnings'] if 'stale: signal_as_of=' in w['message']
    ]
    assert len(stale_warnings) >= 1, (
      f'DATA-05: no stale warning found in state[warnings]; got {post["warnings"]!r}'
    )
    msg = stale_warnings[-1]['message']
    assert '6d old' in msg, (
      f'DATA-05: expected 6d-old in warning message, got {msg!r}'
    )
    assert '(threshold=3d)' in msg, (
      f'DATA-05: expected (threshold=3d) in warning message, got {msg!r}'
    )
    assert '[Fetch] WARN' in caplog.text, (
      'DATA-05: expected [Fetch] WARN log line at WARNING level'
    )

  def test_fetch_failure_exits_nonzero_no_save_state(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''ERR-01 / D-03: DataFetchError during fetch exits 2 and leaves state.json
    untouched (no partial writes). Asserts the typed-exception boundary in
    main() maps DataFetchError → exit 2 AND the [Fetch] ERROR log line.
    '''
    caplog.set_level(logging.ERROR)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    state_json = tmp_path / 'state.json'
    _seed_fresh_state(state_json)
    mtime_before = state_json.stat().st_mtime_ns

    def always_fail(sym, **_kw):
      raise DataFetchError('simulated network down')
    monkeypatch.setattr(main.data_fetcher, 'fetch_ohlcv', always_fail)

    rc = main.main(['--once'])
    assert rc == 2, (
      f'ERR-01: expected exit 2 for DataFetchError, got {rc}'
    )
    assert state_json.stat().st_mtime_ns == mtime_before, (
      'ERR-01: state.json mtime must be unchanged when fetch fails'
    )
    assert '[Fetch] ERROR:' in caplog.text, (
      'ERR-01: expected [Fetch] ERROR: log line'
    )
    assert 'simulated network down' in caplog.text, (
      'ERR-01: expected DataFetchError message to appear in logs'
    )

  # =========================================================================
  # Phase 5 D-06 dashboard integration tests (05-03-PLAN Task 3)
  # =========================================================================

  @pytest.mark.freeze_time('2026-04-22 09:00:03+08:00')
  def test_run_daily_check_renders_dashboard(
      self, tmp_path, monkeypatch) -> None:
    '''D-06 Phase 5: run_daily_check calls dashboard.render_dashboard AFTER
    save_state; dashboard.html exists on disk post-run (VALIDATION row 05-03-T3).
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    rc = main.main(['--once'])
    assert rc == 0

    dashboard_html = tmp_path / 'dashboard.html'
    assert dashboard_html.exists(), (
      'D-06: dashboard.html must exist on disk after run_daily_check succeeds'
    )
    # Smoke-check: valid HTML + palette bg + SRI.
    content = dashboard_html.read_text()
    assert content.startswith('<!DOCTYPE html>'), 'must be well-formed HTML'
    assert '#0f1117' in content, 'DASH-09: palette bg must be present'
    assert 'sha384-MH1axGwz' in content, 'DASH-02: Chart.js SRI must be present'

  def test_dashboard_failure_never_crashes_run(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''D-06: if dashboard.render_dashboard raises at CALL TIME, run_daily_check
    logs at WARNING and returns 0. State was already saved — cosmetic failure
    must not abort the run (VALIDATION row 05-03-T3).

    C-2 reviews: covers the CALL-TIME failure branch. Import-time failures
    are covered by test_dashboard_import_time_failure_never_crashes_run
    below, which monkeypatches sys.modules so the in-helper `import
    dashboard` raises instead of the render call.
    '''
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    # Force render_dashboard to raise at CALL TIME.
    # C-2 reviews: monkeypatch target is `dashboard.render_dashboard` (the
    # module attribute on the real dashboard module — the in-helper `import
    # dashboard` reuses sys.modules['dashboard']). NOT
    # `main.dashboard.render_dashboard`, which does not exist once the
    # module-top import is removed per C-2.
    import dashboard as _dashboard_module_for_patch

    def _raise(*args, **kwargs):
      raise RuntimeError('simulated render failure')
    monkeypatch.setattr(_dashboard_module_for_patch, 'render_dashboard', _raise)

    rc = main.main(['--once'])
    assert rc == 0, 'D-06: dashboard failure must NOT change exit code'

    # State was saved (pre-render step); dashboard was not.
    state_json = tmp_path / 'state.json'
    assert state_json.exists(), 'state.json must exist (saved pre-dashboard)'
    assert not (tmp_path / 'dashboard.html').exists(), (
      'dashboard.html must NOT exist — render was forced to raise'
    )
    # WARNING log with [Dashboard] prefix + exception class name.
    assert '[Dashboard] render failed' in caplog.text, (
      'D-06: failure must log at WARNING with [Dashboard] prefix'
    )
    assert 'RuntimeError' in caplog.text, 'exception type must be in log message'

  def test_dashboard_import_time_failure_never_crashes_run(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''C-2 reviews: an import-time error in dashboard.py (syntax error,
    missing sub-import, etc.) MUST be caught by the same `except Exception`
    that catches runtime render failures. The in-helper `import dashboard`
    statement makes this possible.

    Strategy: replace sys.modules['dashboard'] with an object whose
    attribute access raises. When `_render_dashboard_never_crash` runs
    `import dashboard`, Python reloads via the fake, and when the helper
    tries to reach `dashboard.render_dashboard`, attribute access fails —
    the try/except catches, and the run completes with rc == 0.

    If this test ever fails, the most likely cause is that a regression
    moved `import dashboard` back to main.py module scope — fix by moving
    it back inside the helper (C-2 reviews).
    '''
    import sys
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    class _BrokenDashboard:
      def __getattr__(self, name):
        raise ImportError(
          f'simulated import-time failure: cannot access {name!r}'
        )
    original = sys.modules.get('dashboard')
    sys.modules['dashboard'] = _BrokenDashboard()
    try:
      rc = main.main(['--once'])
    finally:
      if original is not None:
        sys.modules['dashboard'] = original
      else:
        sys.modules.pop('dashboard', None)

    assert rc == 0, (
      'C-2 reviews: dashboard IMPORT-time failure must NOT change exit code'
    )
    # State must still be on disk — save_state runs before the dashboard call.
    assert (tmp_path / 'state.json').exists(), (
      'state.json must exist (saved pre-dashboard)'
    )
    assert not (tmp_path / 'dashboard.html').exists(), (
      'dashboard.html must NOT exist — import was forced to fail'
    )
    assert '[Dashboard] render failed' in caplog.text, (
      'C-2 reviews: import-time failure must log the same way as '
      'runtime failure — single WARN line under [Dashboard] prefix'
    )

  @pytest.mark.freeze_time('2026-04-22 09:00:03+08:00')
  def test_test_flag_leaves_dashboard_html_mtime_unchanged(
      self, tmp_path, monkeypatch) -> None:
    '''C-3 reviews: --test is STRUCTURALLY read-only per CLI-01 + CLAUDE.md.
    Dashboard renders ONLY on the non-test path. This test mirrors
    test_test_flag_leaves_state_json_mtime_unchanged from Phase 4 but for
    the dashboard.html artefact.

    Pre-create dashboard.html with known bytes; run --test; assert the
    file is unchanged (same mtime + same bytes).
    '''
    import time as _time
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    # Pre-populate dashboard.html so we have a baseline mtime + bytes.
    dash = tmp_path / 'dashboard.html'
    original_bytes = b'<!DOCTYPE html><html><body>ORIGINAL</body></html>'
    dash.write_bytes(original_bytes)
    original_mtime = dash.stat().st_mtime

    # Wait ~1.1s so any filesystem mtime bump from a mis-placed render
    # call would be detectable (most filesystems mtime is 1s resolution).
    _time.sleep(1.1)

    rc = main.main(['--test'])
    assert rc == 0

    # C-3 contract: dashboard.html untouched under --test.
    assert dash.exists(), 'dashboard.html must still exist'
    assert dash.read_bytes() == original_bytes, (
      'C-3 reviews: --test must NOT rewrite dashboard.html — '
      'rendering is a disk mutation forbidden by CLI-01 structural read-only.'
    )
    assert dash.stat().st_mtime == original_mtime, (
      'C-3 reviews: --test must NOT bump dashboard.html mtime — '
      'rendering is a disk mutation forbidden by CLI-01 structural read-only.'
    )


class TestEmailNeverCrash:
  '''D-15 + NOTF-07 + NOTF-08: email dispatch failures never crash the run.

  Mirror of TestOrchestrator::test_dashboard_failure_never_crashes_run (runtime)
  and ::test_dashboard_import_time_failure_never_crashes_run (import-time).
  '''

  def test_email_runtime_failure_never_crashes_run(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''D-15: if notifier.send_daily_email raises at CALL TIME, main returns 0
    and caplog has `[Email] send failed`. State was already saved.
    '''
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    import notifier as _notifier_module

    def _raise(*args, **kwargs):
      raise RuntimeError('simulated send failure')

    monkeypatch.setattr(_notifier_module, 'send_daily_email', _raise)

    rc = main.main(['--force-email'])
    assert rc == 0, 'D-15: email failure must NOT change exit code'
    assert '[Email] send failed' in caplog.text
    assert 'RuntimeError' in caplog.text

  def test_email_import_time_failure_never_crashes_run(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''C-2 reviews: import-time notifier failure MUST be caught by the same
    `except Exception` that catches runtime dispatch failures. The in-helper
    `import notifier` statement makes this possible.

    Strategy: replace sys.modules['notifier'] with an object whose attribute
    access raises ImportError. When `_send_email_never_crash` runs
    `import notifier`, Python reloads via the fake; attribute access on
    `notifier.send_daily_email` fails; the try/except catches; rc == 0.
    '''
    import sys
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    class _BrokenNotifier:
      def __getattr__(self, name):
        raise ImportError(
          f'simulated import-time failure: cannot access {name!r}',
        )

    original = sys.modules.get('notifier')
    sys.modules['notifier'] = _BrokenNotifier()
    try:
      rc = main.main(['--force-email'])
    finally:
      if original is not None:
        sys.modules['notifier'] = original
      else:
        sys.modules.pop('notifier', None)

    assert rc == 0, 'C-2: import-time notifier failure must NOT crash'
    assert '[Email] send failed' in caplog.text


class TestRunDailyCheckTupleReturn:
  '''Phase 6 D-05 + RESEARCH §9: run_daily_check returns 4-tuple
  (rc, state, old_signals, run_date).
  '''

  def test_run_daily_check_returns_4_tuple(
      self, tmp_path, monkeypatch) -> None:
    from datetime import datetime as _dt
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    result = main.run_daily_check(_make_args(once=True))
    assert isinstance(result, tuple), (
      f'expected tuple return; got {type(result).__name__}'
    )
    assert len(result) == 4, f'expected 4-tuple; got len={len(result)}'
    rc, state, old_signals, run_date = result
    assert rc == 0
    assert isinstance(state, dict), 'state must be a dict on success path'
    assert isinstance(old_signals, dict), 'old_signals must be a dict'
    assert isinstance(run_date, _dt)
    assert run_date.tzinfo is not None, 'run_date must be timezone-aware'

  def test_run_daily_check_test_mode_returns_in_memory_state(
      self, tmp_path, monkeypatch) -> None:
    '''--test early-return: state is non-None (in-memory compute output);
    state.json mtime unchanged.
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)  # C-4
    state_json = tmp_path / 'state.json'
    _seed_fresh_state(state_json)
    mtime_before = state_json.stat().st_mtime_ns
    _install_fixture_fetch(monkeypatch)

    rc, state, old_signals, run_date = main.run_daily_check(_make_args(test=True))
    assert rc == 0
    assert state is not None, '--test must return the in-memory post-compute state'
    assert old_signals is not None
    assert run_date is not None
    assert state_json.stat().st_mtime_ns == mtime_before, (
      'CLI-01: --test early-return must NOT call save_state'
    )


class TestLoggerConfig:
  '''Pitfall 4: main() configures logging via basicConfig(force=True).

  Wave 0 scaffolds; Wave 3 fills body (04-04-PLAN.md).
  '''

  def test_main_configures_logging_with_force_true(
      self, tmp_path, monkeypatch) -> None:
    '''Pitfall 4: `main()` calls `logging.basicConfig(..., force=True)`.

    Proof-by-consequence: install a dummy handler on the root logger BEFORE
    main() runs; assert that after main() returns the dummy is GONE —
    force=True is the only way that can happen because basicConfig is
    otherwise a no-op when the root logger already has handlers attached.

    This test deliberately does NOT monkeypatch main.logging.basicConfig
    (unlike the caplog-asserting tests above per the C-4 strategy) — the
    whole point here is to verify basicConfig actually runs and applies
    force=True semantics.
    '''
    monkeypatch.chdir(tmp_path)
    _seed_fresh_state(tmp_path / 'state.json')
    _install_fixture_fetch(monkeypatch)

    class _DummyHandler(logging.Handler):
      def emit(self, record):
        pass

    root = logging.getLogger()
    dummy = _DummyHandler()
    root.addHandler(dummy)
    try:
      main.main(['--test'])
      assert dummy not in root.handlers, (
        'Pitfall 4: basicConfig(force=True) should have removed the '
        'dummy handler installed before main() ran. If the dummy is still '
        'attached, main() is NOT using force=True.'
      )
      assert root.level == logging.INFO, (
        f'Pitfall 4: expected root level INFO after main(), got {root.level}'
      )
    finally:
      if dummy in root.handlers:
        root.removeHandler(dummy)


# =========================================================================
# Phase 8 Task 2 — CLI CONF flags + _handle_reset interactive Q&A
# =========================================================================


class TestResetFlags:
  '''Phase 8 D-09/D-10/D-11/D-12/D-13 + T-08-12:
  explicit-flag happy path + validation + choices + combo rules + isfinite.
  '''

  def test_reset_with_all_three_flags_writes_state(
      self, tmp_path, monkeypatch) -> None:
    '''Test 1: all flags present + RESET_CONFIRM=YES → state.json has
    initial_account=50000.0 AND contracts matches flags.
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setenv('RESET_CONFIRM', 'YES')
    rc = main.main([
      '--reset',
      '--initial-account', '50000',
      '--spi-contract', 'spi-mini',
      '--audusd-contract', 'audusd-standard',
    ])
    assert rc == 0
    s = json.loads((tmp_path / 'state.json').read_text())
    assert s['initial_account'] == 50000.0
    assert s['contracts'] == {
      'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard',
    }

  def test_initial_account_below_1000_rejected(
      self, tmp_path, monkeypatch, capsys) -> None:
    '''Test 2: --initial-account 500 → exit 1 + stderr mentions "at least $1,000".'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setenv('RESET_CONFIRM', 'YES')
    rc = main.main([
      '--reset',
      '--initial-account', '500',
      '--spi-contract', 'spi-mini',
      '--audusd-contract', 'audusd-standard',
    ])
    assert rc == 1
    err = capsys.readouterr().err
    assert 'at least $1,000' in err

  def test_invalid_spi_contract_choice_rejected(
      self, tmp_path, monkeypatch) -> None:
    '''Test 3: --spi-contract spi-bogus → exit 2 (argparse choices).'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    with pytest.raises(SystemExit) as exc:
      main.main([
        '--reset',
        '--initial-account', '50000',
        '--spi-contract', 'spi-bogus',
        '--audusd-contract', 'audusd-standard',
      ])
    assert exc.value.code == 2

  def test_invalid_audusd_contract_choice_rejected(
      self, tmp_path, monkeypatch) -> None:
    '''Test 4: --audusd-contract audusd-bogus → exit 2.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    with pytest.raises(SystemExit) as exc:
      main.main([
        '--reset',
        '--initial-account', '50000',
        '--spi-contract', 'spi-mini',
        '--audusd-contract', 'audusd-bogus',
      ])
    assert exc.value.code == 2

  def test_flag_combo_relaxation_allows_conf_flags_with_reset(
      self, tmp_path, monkeypatch) -> None:
    '''Test 5: D-09 relaxation — CONF flags allowed alongside --reset.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setenv('RESET_CONFIRM', 'YES')
    rc = main.main([
      '--reset',
      '--initial-account', '25000',
      '--spi-contract', 'spi-standard',
      '--audusd-contract', 'audusd-mini',
    ])
    assert rc == 0

  def test_initial_account_without_reset_rejected(
      self, tmp_path, monkeypatch) -> None:
    '''Test 6: --initial-account without --reset → exit 2 + "require --reset".'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    with pytest.raises(SystemExit) as exc:
      main.main(['--initial-account', '50000'])
    assert exc.value.code == 2

  def test_spi_contract_without_reset_rejected(
      self, tmp_path, monkeypatch) -> None:
    '''Test 7: --spi-contract without --reset → exit 2.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    with pytest.raises(SystemExit) as exc:
      main.main(['--spi-contract', 'spi-mini'])
    assert exc.value.code == 2

  def test_reset_combined_with_once_rejected(
      self, tmp_path, monkeypatch) -> None:
    '''Test 8: --reset --once → exit 2 + "cannot be combined" (D-05 preserved).'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    with pytest.raises(SystemExit) as exc:
      main.main(['--reset', '--once'])
    assert exc.value.code == 2

  def test_initial_account_nan_rejected_cli_path(
      self, tmp_path, monkeypatch, capsys) -> None:
    '''Test 18 (T-08-12): --initial-account nan → exit 1 + stderr "finite".'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setenv('RESET_CONFIRM', 'YES')
    rc = main.main([
      '--reset',
      '--initial-account', 'nan',
      '--spi-contract', 'spi-mini',
      '--audusd-contract', 'audusd-standard',
    ])
    assert rc == 1
    err = capsys.readouterr().err
    assert 'finite' in err.lower()

  def test_initial_account_inf_rejected_cli_path(
      self, tmp_path, monkeypatch, capsys) -> None:
    '''T-08-12: +inf rejected on the argparse-flag path.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setenv('RESET_CONFIRM', 'YES')
    rc = main.main([
      '--reset',
      '--initial-account', 'inf',
      '--spi-contract', 'spi-mini',
      '--audusd-contract', 'audusd-standard',
    ])
    assert rc == 1
    err = capsys.readouterr().err
    assert 'finite' in err.lower()


class TestResetInteractive:
  '''Phase 8 D-09: interactive Q&A paths.'''

  def test_reset_interactive_happy_path(
      self, tmp_path, monkeypatch) -> None:
    '''Test 9: TTY + iter inputs → state.json has inputs applied.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('main._stdin_isatty', lambda: True)
    inputs = iter(['50000', 'spi-standard', 'audusd-mini'])
    monkeypatch.setattr('builtins.input', lambda prompt='': next(inputs))
    monkeypatch.setenv('RESET_CONFIRM', 'YES')
    rc = main.main(['--reset'])
    assert rc == 0
    s = json.loads((tmp_path / 'state.json').read_text())
    assert s['initial_account'] == 50000.0
    assert s['contracts'] == {'SPI200': 'spi-standard', 'AUDUSD': 'audusd-mini'}

  def test_reset_interactive_quit_cancels(
      self, tmp_path, monkeypatch, caplog) -> None:
    '''Test 10: first input == 'q' → exit 1, no state.json written.'''
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('main._stdin_isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda prompt='': 'q')
    rc = main.main(['--reset'])
    assert rc == 1
    assert not (tmp_path / 'state.json').exists()
    assert 'cancelled' in caplog.text

  def test_reset_interactive_blank_defaults(
      self, tmp_path, monkeypatch) -> None:
    '''Test 11: all blank inputs → defaults applied.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('main._stdin_isatty', lambda: True)
    inputs = iter(['', '', ''])
    monkeypatch.setattr('builtins.input', lambda prompt='': next(inputs))
    monkeypatch.setenv('RESET_CONFIRM', 'YES')
    rc = main.main(['--reset'])
    assert rc == 0
    s = json.loads((tmp_path / 'state.json').read_text())
    assert s['initial_account'] == 100000.0
    assert s['contracts'] == {'SPI200': 'spi-mini', 'AUDUSD': 'audusd-standard'}

  def test_reset_interactive_dollar_sign_comma_stripping(
      self, tmp_path, monkeypatch) -> None:
    '''Test 12: input '$50,000' → parsed as 50000.0.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('main._stdin_isatty', lambda: True)
    inputs = iter(['$50,000', '', ''])
    monkeypatch.setattr('builtins.input', lambda prompt='': next(inputs))
    monkeypatch.setenv('RESET_CONFIRM', 'YES')
    rc = main.main(['--reset'])
    assert rc == 0
    s = json.loads((tmp_path / 'state.json').read_text())
    assert s['initial_account'] == 50000.0

  def test_reset_interactive_invalid_float_rejected(
      self, tmp_path, monkeypatch, capsys) -> None:
    '''Test 13: input 'abc' → exit 1 + "invalid account value".'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('main._stdin_isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda prompt='': 'abc')
    rc = main.main(['--reset'])
    assert rc == 1
    err = capsys.readouterr().err
    assert 'invalid account value' in err

  def test_reset_interactive_below_1000_rejected(
      self, tmp_path, monkeypatch, capsys) -> None:
    '''Test 14: input '500' → exit 1 + "at least $1,000".'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('main._stdin_isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda prompt='': '500')
    rc = main.main(['--reset'])
    assert rc == 1
    err = capsys.readouterr().err
    assert 'at least $1,000' in err

  def test_reset_interactive_nan_rejected(
      self, tmp_path, monkeypatch, capsys) -> None:
    '''Test 19 (T-08-12 interactive path): input 'nan' → exit 1 + "finite".'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('main._stdin_isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda prompt='': 'nan')
    rc = main.main(['--reset'])
    assert rc == 1
    err = capsys.readouterr().err
    assert 'finite' in err.lower()


class TestResetPreview:
  '''Phase 8 D-12: preview block printed before YES prompt.'''

  def test_preview_shows_new_and_current_values(
      self, tmp_path, monkeypatch, capsys) -> None:
    '''Test 17: stdout contains New values block + Current state.json block.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('main._stdin_isatty', lambda: True)
    # Pre-exist state.json so the "Current state.json" section renders.
    _seed_fresh_state(tmp_path / 'state.json')
    inputs = iter(['50000', 'spi-standard', 'audusd-mini'])
    monkeypatch.setattr('builtins.input', lambda prompt='': next(inputs))
    monkeypatch.setenv('RESET_CONFIRM', 'YES')
    rc = main.main(['--reset'])
    assert rc == 0
    out = capsys.readouterr().out
    assert 'New values:' in out
    assert 'Current state.json:' in out
    assert '$50,000.00' in out
    assert 'SPI200:  spi-standard' in out
    assert 'AUDUSD:  audusd-mini' in out


class TestResetNonTTY:
  '''Phase 8 D-13: non-TTY guard.'''

  def test_non_tty_without_flags_exits_2(
      self, tmp_path, monkeypatch, capsys) -> None:
    '''Test 15: non-TTY + no CONF flags → exit 2 + "Non-interactive shell detected".'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('main._stdin_isatty', lambda: False)
    rc = main.main(['--reset'])
    assert rc == 2
    err = capsys.readouterr().err
    assert 'Non-interactive shell detected' in err

  def test_non_tty_with_explicit_flags_succeeds(
      self, tmp_path, monkeypatch) -> None:
    '''Test 16: non-TTY + all flags + RESET_CONFIRM=YES → exit 0.'''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('main._stdin_isatty', lambda: False)
    monkeypatch.setenv('RESET_CONFIRM', 'YES')
    rc = main.main([
      '--reset',
      '--initial-account', '50000',
      '--spi-contract', 'spi-mini',
      '--audusd-contract', 'audusd-standard',
    ])
    assert rc == 0
