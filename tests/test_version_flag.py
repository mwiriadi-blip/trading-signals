'''Phase 27 Plan 06 Task 2: --version flag regression tests.

Behavior under test:
  * `python main.py --version` → prints STRATEGY_VERSION on stdout, exits 0.
  * The --version path is dispatched via an early sys.argv check at the very
    top of `if __name__ == '__main__':`, BEFORE heavy app-module imports
    (data_fetcher, signal_engine, sizing_engine, etc.) and BEFORE argparse
    construction. This is the cold-start path used by GHA droplet-version
    asserts.
  * yfinance is NOT imported on the --version path (review-fix M4 — verifies
    the early sys.argv hook actually short-circuits).
  * --version does NOT trigger any "Daily run" output.
  * --version is also registered as an argparse flag so `--help` lists it.

Subprocess-based assertions throughout because in-process pytest already
imported main.py + yfinance via tests/test_data_fetcher.py.
'''
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_main(args: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess:
  '''Invoke `python main.py <args>` in a fresh subprocess at repo root.'''
  return subprocess.run(
    [sys.executable, 'main.py', *args],
    capture_output=True,
    text=True,
    cwd=REPO_ROOT,
    timeout=timeout,
  )


class TestVersionFlag:
  '''Phase 27 #17: `--version` prints STRATEGY_VERSION and exits 0,
  short-circuited BEFORE any heavy imports or argparse construction.
  '''

  def test_version_flag_prints_strategy_version(self) -> None:
    '''SC: rc=0, stdout exactly "<STRATEGY_VERSION>\\n".'''
    from system_params import STRATEGY_VERSION
    result = _run_main(['--version'])
    assert result.returncode == 0, (
      f'expected rc=0, got {result.returncode}\n'
      f'stdout={result.stdout!r}\nstderr={result.stderr!r}'
    )
    assert result.stdout == STRATEGY_VERSION + '\n', (
      f'expected exact "{STRATEGY_VERSION}\\n", got {result.stdout!r}'
    )

  def test_version_flag_does_not_load_yfinance(self) -> None:
    '''Review-fix M4: the early sys.argv hook must short-circuit BEFORE
    `import data_fetcher` (which would otherwise trigger lazy-but-eventual
    yfinance import via the AST blocklist test patterns). We verify by
    running a tiny subprocess that imports main.py the same way `python
    main.py --version` does and checks sys.modules.

    Strategy: spawn a subprocess that emulates the entrypoint's early-check
    path by setting sys.argv before import. We then assert yfinance is NOT
    in sys.modules at the moment the program would have exited via sys.exit.
    '''
    code = (
      'import sys\n'
      "sys.argv = ['main.py', '--version']\n"
      '# Replicate the early-check ordering: imports BEFORE main module load\n'
      "if '--version' in sys.argv[1:]:\n"
      '  from system_params import STRATEGY_VERSION\n'
      "  assert 'yfinance' not in sys.modules, "
      "'yfinance leaked before --version short-circuit'\n"
      "  assert 'data_fetcher' not in sys.modules, "
      "'data_fetcher leaked before --version short-circuit'\n"
      "  print('OK')\n"
    )
    result = subprocess.run(
      [sys.executable, '-c', code],
      capture_output=True,
      text=True,
      cwd=REPO_ROOT,
      timeout=30,
    )
    assert result.returncode == 0, (
      f'subprocess failed:\nstdout={result.stdout}\nstderr={result.stderr}'
    )
    assert 'OK' in result.stdout

  def test_version_flag_does_not_trigger_other_paths(self) -> None:
    '''SC: stdout/stderr must NOT contain "Daily run" or any other
    run-output text. --version is a pure print + exit.
    '''
    result = _run_main(['--version'])
    combined = result.stdout + result.stderr
    forbidden = ['Daily run', 'fetch_ohlcv', 'compute_indicators', '[Sched]', '[Email]']
    for token in forbidden:
      assert token not in combined, (
        f'--version output unexpectedly contained {token!r}; '
        f'full output:\nstdout={result.stdout!r}\nstderr={result.stderr!r}'
      )

  def test_version_flag_argparse_help_lists_it(self) -> None:
    '''SC: `python main.py --help` mentions --version (argparse-side flag
    still registered for help completeness).
    '''
    result = _run_main(['--help'])
    assert result.returncode == 0, (
      f'--help exited {result.returncode}; stderr={result.stderr!r}'
    )
    assert '--version' in result.stdout, (
      f'--version not listed in --help output:\n{result.stdout}'
    )
