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


class TestLoopHappyPathDispatch:
  '''Regression coverage for the 2026-04-29 silent-skip bug.

  `_run_daily_check_caught` is the scheduler-loop never-crash wrapper. Before
  this regression test landed, the wrapper called `job(args)` and discarded
  the returned `(state, old_signals, run_date)` tuple via `rc, _, _, _ = ...`,
  so `_dispatch_email_and_maintain_warnings` was never invoked and the
  production droplet daemon silently stopped sending the daily 08:00 AWST
  email. CLI flag paths (`--force-email`, `--test`) were unaffected because
  they dispatch directly in `main()`. The original D-02 tests in
  TestLoopErrorHandling only exercised the exception/non-zero-rc branches —
  the rc==0 happy path was uncovered.

  Tests below pin the dispatch call shape so the regression cannot recur:
    - rc==0 with full state → dispatch called once with persist=True, is_test=False
    - rc==0 with state=None (weekend skip) → dispatch NOT called
    - rc != 0 → dispatch NOT called (also asserted in TestLoopErrorHandling)
  '''

  def _patched_dispatch(self, monkeypatch):
    '''Return a recording stand-in for _dispatch_email_and_maintain_warnings.'''
    calls: list[dict] = []

    def _record(state, old_signals, run_date, *, is_test=False, persist=True):
      calls.append({
        'state': state,
        'old_signals': old_signals,
        'run_date': run_date,
        'is_test': is_test,
        'persist': persist,
      })

    monkeypatch.setattr(
      main_module, '_dispatch_email_and_maintain_warnings', _record,
    )
    return calls

  def test_happy_path_dispatches_email(self, monkeypatch) -> None:
    calls = self._patched_dispatch(monkeypatch)
    state = {'account': 100000.0, 'positions': {}, 'signals': {}}
    old_signals = {'^AXJO': 0, 'AUDUSD=X': 0}
    run_date = 'fake-run-date-sentinel'

    def _job(args):
      return (0, state, old_signals, run_date)

    main_module._run_daily_check_caught(_job, argparse.Namespace())

    assert len(calls) == 1, (
      f'expected exactly one dispatch call on rc==0 happy path, got {len(calls)}'
    )
    assert calls[0]['state'] is state
    assert calls[0]['old_signals'] is old_signals
    assert calls[0]['run_date'] is run_date
    assert calls[0]['is_test'] is False, 'scheduler path is never test mode'
    assert calls[0]['persist'] is True, 'scheduler path always persists'

  def test_weekend_skip_does_not_dispatch(self, monkeypatch) -> None:
    calls = self._patched_dispatch(monkeypatch)

    # run_daily_check returns (0, None, None, run_date) on weekend skip.
    def _weekend_job(args):
      return (0, None, None, 'sat-run-date')

    main_module._run_daily_check_caught(_weekend_job, argparse.Namespace())

    assert calls == [], (
      'weekend-skip path returns state=None — must NOT dispatch email'
    )

  def test_nonzero_rc_does_not_dispatch(self, monkeypatch) -> None:
    calls = self._patched_dispatch(monkeypatch)

    def _failing_job(args):
      return (2, {'account': 1.0}, {}, 'fake-run-date')

    main_module._run_daily_check_caught(_failing_job, argparse.Namespace())

    assert calls == [], (
      'rc != 0 → daily check failed; must NOT dispatch email'
    )

  def test_exception_path_does_not_dispatch(self, monkeypatch) -> None:
    calls = self._patched_dispatch(monkeypatch)

    def _raising_job(args):
      raise RuntimeError('compute crashed')

    main_module._run_daily_check_caught(_raising_job, argparse.Namespace())

    assert calls == [], 'exception caught → must NOT dispatch email'


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
    # Phase 8 signature update: _handle_reset now takes args.
    monkeypatch.setattr(main_module, '_handle_reset', lambda args: 1)
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

  WORKFLOW_PATH = '.github/workflows/daily.yml.disabled'

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

  def test_daily_workflow_has_timeout_minutes(self) -> None:
    '''Phase 9 IN-01 carry-over from Phase 7 (v1.0-MILESTONE-AUDIT.md §tech_debt).

    Job-level timeout-minutes caps runaway runs so a stuck yfinance fetch, a
    hung Resend retry, or a leaked schedule-loop cannot consume GHA minutes
    indefinitely. 10 minutes is well above the ~2 min happy-path runtime and
    the ~30s crash-email retry budget (Phase 8 D-07).
    '''
    import yaml  # pinned PyYAML==6.0.2 per Wave 0 Phase 7
    with open(self.WORKFLOW_PATH, encoding='utf-8') as fh:
      parsed = yaml.safe_load(fh)
    jobs = parsed.get('jobs') or {}
    daily = jobs.get('daily') or {}
    assert 'timeout-minutes' in daily, (
      'IN-01: jobs.daily.timeout-minutes must be set to cap runaway runs; '
      f'daily job keys: {list(daily.keys())}'
    )
    assert daily['timeout-minutes'] == 10, (
      'IN-01: jobs.daily.timeout-minutes must equal 10 (min-level cap); '
      f'got {daily["timeout-minutes"]!r}'
    )


class TestDeployDocs:
  '''SCHED-06 / D-14..D-16: static validation of docs/DEPLOY.md + README.md.

  07-REVIEWS.md fixes validated by this class:
  - Gemini LOW: README.md contains the GitHub Actions status badge
    (`actions/workflows/daily.yml/badge.svg` substring).
  - Consensus LOW: docs/DEPLOY.md contains the local-dev TZ=UTC note
    (`TZ=UTC` substring inside a Local-development-style section).
  '''

  DEPLOY_PATH = 'docs/DEPLOY.md'
  README_PATH = 'README.md'

  def test_deploy_md_exists(self) -> None:
    import os
    assert os.path.isfile(self.DEPLOY_PATH), (
      f'D-14: {self.DEPLOY_PATH} must exist as operator runbook'
    )

  def test_readme_exists(self) -> None:
    import os
    assert os.path.isfile(self.README_PATH), (
      'Phase 7 top-level README.md must exist'
    )

  def test_deploy_md_has_gha_quickstart(self) -> None:
    with open(self.DEPLOY_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'GitHub Actions' in content
    assert 'Quickstart' in content
    assert 'Settings → Secrets and variables → Actions' in content, (
      'Quickstart must include repo Secrets setup path'
    )

  def test_deploy_md_has_replit_alternative(self) -> None:
    with open(self.DEPLOY_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'Replit' in content
    assert 'Reserved VM' in content, (
      'SCHED-06: Replit Reserved VM section required'
    )
    assert 'Always On' in content, (
      'SCHED-06: Always On requirement required'
    )
    assert 'Autoscale' in content and 'DOES NOT' in content, (
      'Filesystem-persistence caveat must call out Autoscale'
    )

  def test_deploy_md_env_var_contract(self) -> None:
    with open(self.DEPLOY_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'RESEND_API_KEY' in content
    assert 'SIGNALS_EMAIL_TO' in content
    # D-12: ANTHROPIC_API_KEY must be explicitly noted as deferred (not required)
    if 'ANTHROPIC_API_KEY' in content:
      # Allowed if and only if explicitly labelled as superseded / deferred.
      # Naive check: the section header should indicate it is not required.
      assert (
        'deferred' in content.lower()
        or 'superseded' in content.lower()
        or 'not required' in content.lower()
      ), (
        'D-12: ANTHROPIC_API_KEY only allowed if explicitly called out as deferred'
      )

  def test_deploy_md_troubleshooting_section(self) -> None:
    with open(self.DEPLOY_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert '## Troubleshooting' in content or 'Troubleshooting' in content
    # Required troubleshooting entries per Pitfalls 1, 2, 4, 5 + operator recovery:
    required_entries = [
      'no email arrived',           # green-run-no-email (Pitfall + NOTF-08)
      'later than 08:00 AWST',      # Pitfall 5 drift
      'DataFetchError',             # Phase 4 failure mode
      'commit conflict',            # manual-edit conflict
      'Replit',                     # Replit-specific
      'wrong wall-clock',           # Pitfall 1 TZ
      'no state.json commit',       # Pitfall 2 first-run-no-commit
      '[skip ci]',                  # Pitfall 4 knowledge-only
    ]
    for phrase in required_entries:
      assert phrase in content, (
        f'Troubleshooting must cover: "{phrase}"'
      )

  def test_deploy_md_local_dev_tz_note(self) -> None:
    '''07-REVIEWS.md Consensus LOW fix: docs/DEPLOY.md must cover local-dev
    TZ=UTC invariant for default (loop) mode.
    '''
    with open(self.DEPLOY_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'TZ=UTC' in content, (
      '07-REVIEWS.md Consensus LOW: docs/DEPLOY.md must explicitly mention '
      'TZ=UTC for local loop-mode development'
    )
    # The note should explain when loop vs one-shot modes need TZ:
    assert 'Local development' in content or 'local' in content.lower(), (
      'Local-dev section or mention required'
    )

  def test_deploy_md_cost_estimate(self) -> None:
    with open(self.DEPLOY_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'Cost' in content or 'cost' in content
    assert '2000' in content, 'Cost estimate must reference 2000-min free tier'
    assert '21' in content or 'minutes/month' in content, (
      'Cost estimate must show monthly minute consumption'
    )

  def test_readme_points_at_deploy_md(self) -> None:
    with open(self.README_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'docs/DEPLOY.md' in content, (
      'README.md must link to operator runbook'
    )
    assert 'SPEC.md' in content
    assert 'CLAUDE.md' in content

  def test_readme_has_quickstart_commands(self) -> None:
    with open(self.README_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'python main.py --once' in content
    assert 'python main.py --test' in content
    assert 'python main.py --reset' in content
    assert 'python main.py' in content  # default mode

  def test_readme_has_gha_status_badge(self) -> None:
    '''07-REVIEWS.md Gemini LOW fix: README.md must include a GitHub Actions
    workflow status badge pointing at the Daily signal check workflow.
    '''
    with open(self.README_PATH, encoding='utf-8') as fh:
      content = fh.read()
    assert 'actions/workflows/daily.yml/badge.svg' in content, (
      '07-REVIEWS.md Gemini LOW: GitHub Actions status badge must be present '
      'in README.md pointing at .github/workflows/daily.yml'
    )
    # Sanity: the badge must be a clickable link (markdown image inside link syntax).
    assert '[![' in content, (
      'Badge must use `[![alt](img)](link)` markdown pattern'
    )

  def test_deploy_md_length_sane(self) -> None:
    '''D-15: ~150 lines target; allow 120-220 range for flex.'''
    with open(self.DEPLOY_PATH, encoding='utf-8') as fh:
      lines = fh.readlines()
    count = len(lines)
    assert 100 <= count <= 250, (
      f'D-15: docs/DEPLOY.md length {count} outside sane range [100, 250]'
    )


# =========================================================================
# Phase 8 Task 3 — crash-email Layer B integration
# =========================================================================


class TestCrashEmailLayerB:
  '''Phase 8 D-05/D-06/D-07: unhandled exceptions in the schedule-loop
  driver propagate to main()'s outer except and fire the crash-email
  dispatch; Layer A (per-job) is unchanged and does NOT fire crash mail.
  '''

  def test_assertion_error_in_loop_driver_propagates_to_main_catch_all(
      self, tmp_path, monkeypatch) -> None:
    '''D-05/D-07: AssertionError from the loop driver (e.g. UTC tz check)
    is caught by main()'s outer except → crash-email dispatch invoked.
    '''
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)
    monkeypatch.setattr(main_module, '_get_process_tzname', lambda: 'AEST')
    monkeypatch.setattr(main_module, '_run_daily_check_caught',
                        lambda j, a: None)
    monkeypatch.setattr('dotenv.load_dotenv', lambda *a, **kw: False)

    recorded: list = []
    monkeypatch.setattr(
      main_module, '_send_crash_email',
      lambda exc, state=None, now=None: recorded.append((exc, state)),
    )
    rc = main_module.main([])
    assert rc == 1
    assert len(recorded) == 1
    assert isinstance(recorded[0][0], AssertionError)

  def test_layer_a_per_job_error_does_not_fire_crash_email(
      self, monkeypatch, caplog) -> None:
    '''D-02/D-05: per-job errors absorbed by _run_daily_check_caught do
    NOT reach main()'s outer except; crash-email NOT fired.
    '''
    caplog.set_level(logging.WARNING)

    def _raising_job(args):
      raise RuntimeError('per-job boom')

    called: list = []
    monkeypatch.setattr(
      main_module, '_send_crash_email',
      lambda exc, state=None, now=None: called.append(exc),
    )
    main_module._run_daily_check_caught(_raising_job, argparse.Namespace())
    # Layer A caught + logged + loop continues.
    assert any(
      'unexpected error caught' in r.message and '[Sched]' in r.message
      for r in caplog.records
    )
    # Crash email NOT invoked — Layer A is not a crash.
    assert called == []
