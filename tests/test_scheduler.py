'''Phase 7 scheduler tests — Wave 1 body.

Wave 0 (07-01-PLAN.md) created the 6-class skeleton + _FakeScheduler helpers.
Wave 1 (07-02-PLAN.md) populates the bodies per D-01..D-06.
Wave 2 (07-03-PLAN.md) appends TestGHAWorkflow + TestDeployDocs.

Timezone-patching strategy: tests patch `main._get_process_tzname` (the Wave 0
wrapper at `main.py`) instead of `time.tzname` (platform-dependent, sometimes
frozen). Per 07-REVIEWS.md Codex MEDIUM-fix — the wrapper is a regular
module-level function that is always writable via `monkeypatch.setattr`.
'''

import argparse
import logging

import pytest

import main as main_module


class _FakeScheduler:
  '''Minimal schedule-library fake for injection. See 07-RESEARCH.md §Example 6.'''

  def __init__(self) -> None:
    self.registered: list[tuple] = []
    self.run_pending_calls = 0

  def every(self):
    return self

  @property
  def day(self):
    # Real `schedule` library: `.every().day` is a property (no parens), not a
    # method — matches production code `.every().day.at(...)` in
    # _run_schedule_loop. [Rule 1] Wave 0 shipped this as a method; Wave 1
    # fix aligns the fake with the real API surface.
    return self

  def at(self, time_str, *_a, **_kw):
    return _FakeJob(self, time_str)

  def run_pending(self) -> None:
    self.run_pending_calls += 1


class _FakeJob:
  def __init__(self, parent: _FakeScheduler, time_str: str) -> None:
    self.parent = parent
    self.time_str = time_str

  def do(self, fn, *args, **kwargs):
    self.parent.registered.append((self.time_str, fn, args, kwargs))
    return self


class TestWeekdayGate:
  '''D-03: run_daily_check short-circuits on AWST Sat/Sun.'''

  @pytest.mark.freeze_time('2026-04-25T00:00:00+00:00')  # Sat 08:00 AWST = weekday=5
  def test_saturday_skips_fetch_and_compute(self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    fetch_calls: list = []
    monkeypatch.setattr(
      main_module.data_fetcher, 'fetch_ohlcv',
      lambda *a, **kw: fetch_calls.append(a) or None,
    )
    args = argparse.Namespace(
      test=False, reset=False, force_email=False, once=True,
    )
    rc, state, old_signals, run_date = main_module.run_daily_check(args)
    assert rc == 0
    assert state is None
    assert old_signals is None
    assert run_date is not None
    assert run_date.weekday() == 5
    assert fetch_calls == []

  @pytest.mark.freeze_time('2026-04-26T00:00:00+00:00')  # Sun 08:00 AWST = weekday=6
  def test_sunday_skips_fetch_and_compute(self, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    fetch_calls: list = []
    monkeypatch.setattr(
      main_module.data_fetcher, 'fetch_ohlcv',
      lambda *a, **kw: fetch_calls.append(a) or None,
    )
    args = argparse.Namespace(
      test=False, reset=False, force_email=False, once=True,
    )
    rc, state, old_signals, run_date = main_module.run_daily_check(args)
    assert rc == 0
    assert state is None
    assert old_signals is None
    assert run_date is not None
    assert run_date.weekday() == 6
    assert fetch_calls == []

  @pytest.mark.freeze_time('2026-04-27T00:00:00+00:00')  # Mon 08:00 AWST = weekday=0
  def test_monday_proceeds_through_fetch(
    self, tmp_path, monkeypatch, caplog,
  ) -> None:
    '''Monday MUST actually proceed to fetch. 07-REVIEWS.md Codex MEDIUM-fix:
    assert explicitly on fetch_ohlcv call count + arguments, not merely on
    absence of "weekend skip" in logs. Regressions that bypass fetch will
    fail this test loudly.

    Uses committed fixtures so both instrument fetches succeed and the full
    per-symbol loop executes (both tickers appear in fetch_calls). This gives
    us a strong positive assertion on fetch-call count AND argument identity.
    '''
    from pathlib import Path
    import pandas as pd

    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    # Seed fresh state.json so run_daily_check can load/save without issue.
    import state_manager
    state_manager.save_state(state_manager.reset_state(), path=tmp_path / 'state.json')

    fetch_fixture_dir = Path(__file__).parent / 'fixtures' / 'fetch'

    def _load_fixture(name: str) -> pd.DataFrame:
      return pd.read_json(fetch_fixture_dir / name, orient='split')

    fetch_calls: list = []

    def _recorder(sym, **kwargs):
      fetch_calls.append((sym, kwargs))
      if sym == '^AXJO':
        return _load_fixture('axjo_400d.json')
      if sym == 'AUDUSD=X':
        return _load_fixture('audusd_400d.json')
      raise AssertionError(f'unexpected symbol: {sym!r}')

    monkeypatch.setattr(main_module.data_fetcher, 'fetch_ohlcv', _recorder)

    args = argparse.Namespace(
      test=True, reset=False, force_email=False, once=True,
    )
    rc, state, old_signals, run_date = main_module.run_daily_check(args)

    # 07-REVIEWS.md Codex MEDIUM-fix: EXPLICIT fetch-call observation.
    assert run_date.weekday() == 0, f'expected Mon; got weekday={run_date.weekday()}'
    assert len(fetch_calls) == 2, (
      f'CLI-04 / SCHED-03: Monday must fetch both instruments; '
      f'got {len(fetch_calls)} fetch call(s): {fetch_calls}'
    )
    # First positional arg is the ticker — verify both expected symbols appear.
    tickers_fetched = {call_args[0] for call_args in fetch_calls}
    assert '^AXJO' in tickers_fetched, (
      f'SCHED-03: ^AXJO (SPI 200) must be fetched on Mon; got {tickers_fetched}'
    )
    assert 'AUDUSD=X' in tickers_fetched, (
      f'SCHED-03: AUDUSD=X must be fetched on Mon; got {tickers_fetched}'
    )
    # Belt-and-braces: weekend-skip branch must not have fired.
    assert 'weekend skip' not in caplog.text


class TestImmediateFirstRun:
  '''D-04: default mode runs a daily check BEFORE entering the loop.'''

  def test_default_mode_calls_job_once_before_loop(self, monkeypatch) -> None:
    call_order: list[str] = []

    def _fake_caught(job, args) -> None:
      call_order.append('caught')

    def _fake_loop(job, args) -> int:
      call_order.append('loop')
      return 0

    monkeypatch.setattr(main_module, '_run_daily_check_caught', _fake_caught)
    monkeypatch.setattr(main_module, '_run_schedule_loop', _fake_loop)
    monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **kw: False)
    # Default-mode dispatch goes straight to _fake_caught + _fake_loop;
    # no need to touch _get_process_tzname because the real loop never runs.
    rc = main_module.main([])
    assert rc == 0
    assert call_order == ['caught', 'loop']


class TestLoopDriver:
  '''D-01: _run_schedule_loop injection + finite-tick discipline.

  Pitfall 1 mitigation is asserted via `main._get_process_tzname` wrapper
  (Wave 0 surface). Tests patch `main._get_process_tzname` — NEVER
  `time.tzname`, per 07-REVIEWS.md Codex MEDIUM-fix (platform-portable).
  '''

  def test_max_ticks_zero_returns_immediately(self, monkeypatch) -> None:
    monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')
    fake = _FakeScheduler()
    sleeps: list[float] = []
    rc = main_module._run_schedule_loop(
      job=lambda args: (0, None, None, None),
      args=argparse.Namespace(),
      scheduler=fake,
      sleep_fn=sleeps.append,
      tick_budget_s=60.0,
      max_ticks=0,
    )
    assert rc == 0
    assert fake.run_pending_calls == 0
    assert sleeps == []
    assert len(fake.registered) == 1
    assert fake.registered[0][0] == '00:00'

  def test_max_ticks_one_runs_single_cycle(self, monkeypatch) -> None:
    monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')
    fake = _FakeScheduler()
    sleeps: list[float] = []
    rc = main_module._run_schedule_loop(
      job=lambda args: (0, None, None, None),
      args=argparse.Namespace(),
      scheduler=fake,
      sleep_fn=sleeps.append,
      tick_budget_s=60.0,
      max_ticks=1,
    )
    assert rc == 0
    assert fake.run_pending_calls == 1
    assert sleeps == [60.0]

  def test_non_utc_process_raises(self, monkeypatch) -> None:
    monkeypatch.setattr('main._get_process_tzname', lambda: 'AEST')
    with pytest.raises(AssertionError, match='must be UTC'):
      main_module._run_schedule_loop(
        job=lambda args: (0, None, None, None),
        args=argparse.Namespace(),
        scheduler=_FakeScheduler(),
        sleep_fn=lambda _: None,
        max_ticks=1,
      )


class TestLoopErrorHandling:
  '''D-02: _run_daily_check_caught swallows exceptions + returns None.'''

  def test_data_fetch_error_caught_logs_warning(self, caplog) -> None:
    from data_fetcher import DataFetchError

    def _raising_job(args):
      raise DataFetchError('yfinance down')

    caplog.set_level(logging.WARNING)
    main_module._run_daily_check_caught(_raising_job, argparse.Namespace())
    assert any(
      'data-layer failure' in r.message and '[Sched]' in r.message
      for r in caplog.records
    )

  def test_unexpected_exception_caught(self, caplog) -> None:
    def _raising_job(args):
      raise RuntimeError('boom')

    caplog.set_level(logging.WARNING)
    main_module._run_daily_check_caught(_raising_job, argparse.Namespace())
    assert any(
      'unexpected error' in r.message
      and 'RuntimeError' in r.message
      and '[Sched]' in r.message
      for r in caplog.records
    )

  def test_nonzero_rc_logs_warning(self, caplog) -> None:
    caplog.set_level(logging.WARNING)
    main_module._run_daily_check_caught(
      lambda args: (2, None, None, None),
      argparse.Namespace(),
    )
    assert any('rc=2' in r.message and '[Sched]' in r.message for r in caplog.records)


class TestDefaultModeDispatch:
  '''D-05: default mode emits new log line; --once does not.'''

  def test_default_mode_emits_scheduler_entered_log(
    self, tmp_path, monkeypatch, caplog,
  ) -> None:
    # 07-REVIEWS.md Codex MEDIUM-fix: patch `main._get_process_tzname` (Wave 0
    # wrapper, always writable) instead of `time.tzname` (platform-dependent,
    # sometimes frozen).
    monkeypatch.setattr('main._get_process_tzname', lambda: 'UTC')
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **kw: False)
    # Short-circuit the immediate first run so we reach the loop quickly.
    monkeypatch.setattr(main_module, '_run_daily_check_caught', lambda j, a: None)
    # Wrap _run_schedule_loop so it uses a fake scheduler + max_ticks=0 — no hang.
    real_loop = main_module._run_schedule_loop
    fake = _FakeScheduler()

    def _wrap(job, args):
      return real_loop(
        job, args,
        scheduler=fake, sleep_fn=lambda _: None, max_ticks=0,
      )

    monkeypatch.setattr(main_module, '_run_schedule_loop', _wrap)
    rc = main_module.main([])
    assert rc == 0
    assert any(
      'scheduler entered' in r.message
      and '00:00 UTC' in r.message
      and '08:00 AWST' in r.message
      for r in caplog.records
    )
    # Assert deprecated Phase 4 line is NOT present anywhere in the record stream:
    assert all(
      'One-shot mode (scheduler wiring lands in Phase 7)' not in r.message
      for r in caplog.records
    ), 'D-05: Phase 4 stub log line must be deleted from run_daily_check'


class TestDotenvLoading:
  '''D-06: load_dotenv fires at top of main(); local import stays isolated.'''

  def test_main_calls_load_dotenv(self, monkeypatch) -> None:
    called: list[bool] = []

    def _recorder(*_a, **_kw):
      called.append(True)
      return False

    monkeypatch.setattr('dotenv.load_dotenv', _recorder)
    # Short-circuit main() via --reset path so we never hit the schedule loop.
    monkeypatch.setattr(main_module, '_handle_reset', lambda: 1)
    rc = main_module.main(['--reset'])
    assert rc == 1
    assert called == [True]
