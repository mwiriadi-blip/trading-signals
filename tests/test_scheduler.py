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


# =========================================================================
# Wave 2 (07-03-PLAN.md): static validation of .github/workflows/daily.yml
# =========================================================================


class TestGHAWorkflow:
  '''SCHED-05 / D-07..D-11 / Pitfall 2: static validation of daily.yml contract.

  07-REVIEWS.md fixes incorporated:
  - Codex HIGH: `test_workflow_parses_as_yaml` computes the `on:` block via
    `parsed.get('on') or parsed.get(True)` BEFORE any indexing. PyYAML 1.1
    coerces bare `on:` to Python `True`; the old shape (`parsed['on']`
    accessed first) would `KeyError` before the fallback ran.
  - Consensus MEDIUM: no `pytest.importorskip('yaml')` — PyYAML is pinned
    (`PyYAML==6.0.2`) in requirements.txt via Wave 0, so the import is
    guaranteed to succeed.
  '''

  WORKFLOW_PATH = '.github/workflows/daily.yml'

  def test_workflow_file_exists(self) -> None:
    import os
    assert os.path.isfile(self.WORKFLOW_PATH), (
      f'SCHED-05: {self.WORKFLOW_PATH} must exist'
    )

  def test_workflow_parses_as_yaml(self) -> None:
    '''Handles PyYAML 1.1 `on: True` boolean-coercion edge case.

    07-REVIEWS.md Codex HIGH fix: resolve the `on:` block FIRST via
    `.get('on') or .get(True)` to tolerate both spellings, THEN do all
    subsequent assertions via `on_block[...]`. The old shape attempted
    `parsed['on']` before the fallback and would `KeyError` on versions
    that coerce bare `on:` to Python `True`.

    Consensus MEDIUM: PyYAML is pinned in requirements.txt (Wave 0), so
    no `importorskip` is needed here — a missing yaml module is a real
    failure, not a test-env skip.
    '''
    import yaml  # guaranteed available — PyYAML==6.0.2 pinned in Wave 0
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      parsed = yaml.safe_load(fh)
    assert parsed is not None, 'daily.yml parsed to None — file empty or malformed'
    assert parsed.get('name') == 'Daily signal check', (
      f"SCHED-05: workflow name must be 'Daily signal check'; "
      f"got {parsed.get('name')!r}"
    )

    # 07-REVIEWS.md Codex HIGH fix: compute on_block FIRST with fallback,
    # THEN assert. Do NOT touch parsed['on'] before this line.
    on_block = parsed.get('on') or parsed.get(True)
    assert on_block is not None, (
      "on: block missing (checked both str 'on' and bool True keys); "
      f"top-level keys: {list(parsed.keys())}"
    )
    assert 'schedule' in on_block, (
      f"SCHED-01: schedule: trigger missing from on: block; "
      f"on_block keys: {list(on_block.keys())}"
    )
    assert 'workflow_dispatch' in on_block, (
      f"D-08: workflow_dispatch: trigger missing from on: block; "
      f"on_block keys: {list(on_block.keys())}"
    )

  def test_cron_schedule_is_0_0_mon_fri(self) -> None:
    import re
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert re.search(r"cron:\s*'0 0 \* \* 1-5'", content), (
      "SCHED-01: cron line must be exactly '0 0 * * 1-5' (single-quoted)"
    )

  def test_workflow_dispatch_present(self) -> None:
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'workflow_dispatch:' in content, (
      'D-08: workflow_dispatch manual trigger required'
    )

  def test_permissions_contents_write(self) -> None:
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'permissions:' in content
    assert 'contents: write' in content, (
      'D-07: permissions.contents: write required for git-auto-commit-action'
    )
    assert 'issues: write' not in content, (
      'Principle of least privilege: do not grant issues write access'
    )
    assert 'pull-requests: write' not in content, (
      'Principle of least privilege: do not grant pull-requests write access'
    )

  def test_concurrency_group_serialises(self) -> None:
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'concurrency:' in content
    assert 'group: trading-signals' in content
    assert 'cancel-in-progress: false' in content, (
      'D-07: in-flight runs must not be cancelled by dispatch overlap'
    )

  def test_setup_python_cache_and_version_file(self) -> None:
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'actions/setup-python@v5' in content
    assert "python-version-file: '.python-version'" in content, (
      'D-09: .python-version pyenv pin consumed by setup-python'
    )
    assert "cache: 'pip'" in content, 'D-09: pip cache required'
    assert 'cache-dependency-path: requirements.txt' in content, (
      'D-09: cache-key scoped to requirements.txt'
    )

  def test_checkout_action_pinned(self) -> None:
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'actions/checkout@v4' in content, 'D-07: actions/checkout@v4 pin'

  def test_run_step_uses_main_once(self) -> None:
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'python main.py --once' in content, (
      'SCHED-04: GHA uses --once mode (one-shot + exit); not default loop mode'
    )

  def test_env_block_names_both_secrets(self) -> None:
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'RESEND_API_KEY:' in content and '${{ secrets.RESEND_API_KEY }}' in content
    assert 'SIGNALS_EMAIL_TO:' in content and '${{ secrets.SIGNALS_EMAIL_TO }}' in content
    # Principle of least privilege — no bulk ${{ secrets }} mapping:
    assert 'env: ${{ secrets' not in content, (
      'D-12: explicit secret mapping required; no bulk ${{ secrets }} exposure'
    )

  def test_git_auto_commit_force_add_and_if_success(self) -> None:
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'stefanzweifel/git-auto-commit-action@v5' in content, (
      'D-10: v5 major-tag pin'
    )
    assert 'if: success()' in content, (
      'D-11: no commit on job failure'
    )
    assert 'file_pattern: state.json' in content, (
      'D-10: commit state.json only'
    )
    assert "add_options: '-f'" in content, (
      'Pitfall 2: state.json is gitignored; add_options: -f required'
    )
    assert "commit_message: 'chore(state): daily signal update [skip ci]'" in content, (
      'D-10: canonical commit message with [skip ci]'
    )
    assert 'commit_user_name:  github-actions[bot]' in content or \
           'commit_user_name: github-actions[bot]' in content
    assert '41898282+github-actions[bot]@users.noreply.github.com' in content, (
      'D-10: canonical bot email for attribution'
    )

  def test_no_ssh_or_pat_token_references(self) -> None:
    '''Security: no leaked SSH keys or PAT references in the workflow.'''
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      content = fh.read()
    # Default GITHUB_TOKEN is sufficient; explicit PAT should not be present.
    assert 'ssh-key:' not in content
    assert 'SSH_PRIVATE_KEY' not in content
    # Sanity check: no ANTHROPIC_API_KEY references per D-12 ROADMAP amendment
    assert 'ANTHROPIC_API_KEY' not in content
