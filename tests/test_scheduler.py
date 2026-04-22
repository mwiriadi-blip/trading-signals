'''Phase 7 scheduler tests — Wave 0 scaffold.

Wave 0 (07-01-PLAN.md) creates the 6-class skeleton + _FakeScheduler helpers.
Wave 1 (07-02-PLAN.md) populates the bodies per D-01..D-06.
Wave 2 (07-03-PLAN.md) appends TestGHAWorkflow + TestDeployDocs.

xfail(strict=True) on each scaffold test means: Wave 0 passes (fails as
expected); if Wave 1 accidentally leaves a scaffold test behind without
removing the xfail marker, the runner reports XPASS and fails the suite.
'''

import argparse  # noqa: F401 — Wave 1 uses argparse.Namespace in the filled tests
import logging  # noqa: F401 — Wave 1 uses caplog assertions through logging

import pytest

import main as main_module  # noqa: F401 — Wave 1 patches attrs on main_module


class _FakeScheduler:
  '''Minimal schedule-library fake for injection. See 07-RESEARCH.md §Example 6.'''

  def __init__(self) -> None:
    self.registered: list[tuple] = []
    self.run_pending_calls = 0

  def every(self):
    return self

  def day(self):
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
  '''D-04: default mode runs a daily check BEFORE entering the loop. Wave 1 fills body.'''

  @pytest.mark.xfail(reason='Wave 1 lands body per 07-02-PLAN.md D-04', strict=True)
  def test_scaffold_placeholder(self) -> None:
    raise NotImplementedError('Wave 1')


class TestLoopDriver:
  '''D-01: _run_schedule_loop injection + finite-tick discipline. Wave 1 fills body.'''

  @pytest.mark.xfail(reason='Wave 1 lands body per 07-02-PLAN.md D-01', strict=True)
  def test_scaffold_placeholder(self) -> None:
    raise NotImplementedError('Wave 1')


class TestLoopErrorHandling:
  '''D-02: _run_daily_check_caught swallows exceptions + returns None. Wave 1 fills body.'''

  @pytest.mark.xfail(reason='Wave 1 lands body per 07-02-PLAN.md D-02', strict=True)
  def test_scaffold_placeholder(self) -> None:
    raise NotImplementedError('Wave 1')


class TestDefaultModeDispatch:
  '''D-05: default mode emits new log line; --once does not. Wave 1 fills body.'''

  @pytest.mark.xfail(reason='Wave 1 lands body per 07-02-PLAN.md D-05', strict=True)
  def test_scaffold_placeholder(self) -> None:
    raise NotImplementedError('Wave 1')


class TestDotenvLoading:
  '''D-06: load_dotenv fires at top of main(); local import stays isolated. Wave 1 fills body.'''

  @pytest.mark.xfail(reason='Wave 1 lands body per 07-02-PLAN.md D-06', strict=True)
  def test_scaffold_placeholder(self) -> None:
    raise NotImplementedError('Wave 1')
