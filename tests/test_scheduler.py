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
  '''D-03: run_daily_check short-circuits on AWST Sat/Sun. Wave 1 fills body.'''

  @pytest.mark.xfail(reason='Wave 1 lands body per 07-02-PLAN.md D-03', strict=True)
  def test_scaffold_placeholder(self) -> None:
    raise NotImplementedError('Wave 1')


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
  '''D-05: default mode emits new log line; --once does not. Wave 1 fills body.'''

  @pytest.mark.xfail(reason='Wave 1 lands body per 07-02-PLAN.md D-05', strict=True)
  def test_scaffold_placeholder(self) -> None:
    raise NotImplementedError('Wave 1')


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
