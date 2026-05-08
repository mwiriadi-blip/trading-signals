'''Phase 27 Plan 13 — main.py split parity tests.

Locks in the file-size + re-export contract from the plan:
  - main.py is a thin entry-point shim (<200 LOC).
  - python main.py --version + --help still work post-split.
  - main.py re-exports every symbol that tests reference via main.X.
  - main.py re-exports every module-attr that tests monkeypatch via
    `monkeypatch.setattr(main.<modname>, ...)` or
    `monkeypatch.setattr('main.<modname>.<attr>', ...)`.
  - main._LAST_LOADED_STATE proxy works via state_actions accessors.
  - Every new module stays under 550 LOC (plan §M1 ±10% tolerance).
'''
import pathlib
import subprocess
import sys


def test_main_py_is_thin() -> None:
  '''main.py must remain a thin entry+re-export shim.'''
  loc = pathlib.Path('main.py').read_text().count('\n')
  assert loc < 200, f'main.py exceeded thin shim budget: {loc}'


def test_cli_version_works() -> None:
  '''python main.py --version prints STRATEGY_VERSION and exits 0.'''
  r = subprocess.run(
    [sys.executable, 'main.py', '--version'],
    capture_output=True, text=True, timeout=30,
  )
  assert r.returncode == 0
  assert r.stdout.strip().startswith('v')


def test_cli_help_works() -> None:
  '''python main.py --help lists --once + --version (locked CLI surface).'''
  r = subprocess.run(
    [sys.executable, 'main.py', '--help'],
    capture_output=True, text=True, timeout=30,
  )
  assert r.returncode == 0
  assert '--once' in r.stdout
  assert '--version' in r.stdout


def test_main_re_exports_symbols() -> None:
  '''main.py must re-export every symbol tests reference via main.X.'''
  import main
  # plan §re-export manifest
  for name in [
    '_build_parser', '_validate_flag_combo', '_mode_label',  # cli_parser
    '_stdin_isatty', '_handle_reset', '_prompt_or_default',  # interactive
    '_get_process_tzname', '_run_daily_check_caught',         # scheduler_driver
    '_run_schedule_loop',
    '_send_email_never_crash', '_build_crash_state_summary',  # crash_boundary
    '_send_crash_email',
    '_render_dashboard_never_crash', '_closed_trade_to_record',  # daily_run_helpers
    'run_daily_check', '_evaluate_paper_trade_alerts',           # daily_loop
    '_dispatch_email_and_maintain_warnings', '_push_state_to_git',
    'main',                                                       # entry point
  ]:
    assert hasattr(main, name), f'{name} missing from main.py shim'


def test_main_re_exports_modules() -> None:
  '''Plan 27-13 agreed-2: main.data_fetcher / main.signal_engine /
  main.sizing_engine / main.state_manager / main.dashboard / main.logging
  preserved as module-attribute paths for monkeypatch.
  '''
  import main
  for modname in [
    'data_fetcher', 'signal_engine', 'sizing_engine',
    'state_manager', 'dashboard', 'logging',
  ]:
    assert hasattr(main, modname), f'main.{modname} missing'


def test_last_loaded_state_proxy_works() -> None:
  '''Plan 27-13 agreed-2: main._LAST_LOADED_STATE round-trip through the
  state_actions accessor pair.
  '''
  import main
  import state_actions

  # Setter on state_actions writes through to main.
  state_actions._set_last_loaded_state({'test': 'value'})
  assert main._LAST_LOADED_STATE == {'test': 'value'}

  # Direct write to main.X is observed by the state_actions getter
  # (preserves the legacy `main._LAST_LOADED_STATE = X` reset path used
  # by tests/test_main.py::TestCrashEmailBoundary).
  main._LAST_LOADED_STATE = {'fresh': 'reset'}
  assert state_actions._get_last_loaded_state() == {'fresh': 'reset'}

  # Restore.
  main._LAST_LOADED_STATE = None
  state_actions._set_last_loaded_state(None)


def test_new_modules_under_500_loc() -> None:
  '''Plan §M1: every new module under 500 LOC (±10% = 550 ceiling).'''
  files = [
    'cli_parser.py', 'interactive.py', 'scheduler_driver.py',
    'crash_boundary.py', 'state_actions.py', 'daily_loop.py',
    'daily_run.py', 'daily_run_helpers.py', 'paper_trade_alerts.py',
  ]
  too_large = []
  for f in files:
    loc = pathlib.Path(f).read_text().count('\n')
    if loc >= 550:
      too_large.append(f'{f}={loc}')
  assert not too_large, (
    f'modules over 550 LOC budget (plan §M1 ±10%): {too_large}'
  )


def test_dispatch_impl_relocated_to_crash_boundary() -> None:
  '''Plan 27-12 agreed-3: _dispatch_email_and_maintain_warnings_impl
  relocates from main.py:1638 to crash_boundary.py.
  '''
  main_src = pathlib.Path('main.py').read_text()
  cb_src = pathlib.Path('crash_boundary.py').read_text()
  # Public wrapper still on main via re-export from daily_loop, but the
  # IMPL must NOT be defined inline in main.py.
  assert 'def _dispatch_email_and_maintain_warnings_impl(' not in main_src, (
    'impl must NOT live in main.py (Plan 27-13 agreed-3 requires '
    'relocation to crash_boundary.py).'
  )
  assert 'def _dispatch_email_and_maintain_warnings_impl(' in cb_src, (
    'impl must be defined in crash_boundary.py per agreed-3.'
  )
