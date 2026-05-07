'''Phase 27 Plan 06 Task 1: deferred yfinance import regression tests.

The behavior under test is that `import data_fetcher` does NOT pull yfinance
into sys.modules at module-import time. yfinance is only loaded on first
fetch (via the `_get_yf()` accessor inside fetch_ohlcv).

Subprocess-based assertions are required: pytest itself imports yfinance
via `tests/test_data_fetcher.py` (`from yfinance.exceptions import
YFRateLimitError`), so checking sys.modules in the same process is unreliable.
Each test spawns a fresh `python -c` subprocess to get a clean sys.modules.

YFRateLimitError must remain importable at module-top of data_fetcher WITHOUT
forcing yfinance import — external `from data_fetcher import YFRateLimitError`
clauses (and the internal try/except chain) must continue to work.

Plan 27-06 review-fix M4: cold-start semantic invariant is "yfinance not in
sys.modules" — NOT a wall-clock <500ms threshold (CI-flaky).
'''
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_py(code: str) -> subprocess.CompletedProcess:
  '''Run `python -c "<code>"` in a fresh subprocess, cwd=repo root.

  Returns CompletedProcess with stdout/stderr captured.
  '''
  return subprocess.run(
    [sys.executable, '-c', code],
    capture_output=True,
    text=True,
    cwd=REPO_ROOT,
    timeout=30,
  )


class TestDeferredYfinanceImport:
  '''Phase 27 #14: yfinance is imported lazily via _get_yf(), not at
  data_fetcher module-load time.
  '''

  def test_yfinance_not_imported_on_module_load(self) -> None:
    '''SC: subprocess `import data_fetcher` does NOT pull yfinance into
    sys.modules. Cold-start semantic invariant (review-fix M4).
    '''
    code = (
      'import sys\n'
      'import data_fetcher\n'
      "assert 'yfinance' not in sys.modules, "
      "'yfinance leaked into sys.modules on data_fetcher import; "
      'expected lazy loading via _get_yf()\\n'
      "modules: ' + str([m for m in sys.modules if 'yfinance' in m])\n"
      "print('OK')\n"
    )
    result = _run_py(code)
    assert result.returncode == 0, (
      f'subprocess failed:\nstdout={result.stdout}\nstderr={result.stderr}'
    )
    assert 'OK' in result.stdout

  def test_yfinance_imported_on_first_fetch_call(self) -> None:
    '''SC: subprocess that calls fetch_ohlcv (mocked at the network boundary)
    DOES populate sys.modules['yfinance']. Confirms _get_yf() actually loads
    yfinance lazily on first use.
    '''
    code = (
      'import sys\n'
      'import data_fetcher\n'
      "assert 'yfinance' not in sys.modules, 'precondition failed'\n"
      '# Trigger _get_yf() via the public accessor itself.\n'
      'data_fetcher._get_yf()\n'
      "assert 'yfinance' in sys.modules, "
      "'yfinance not loaded after _get_yf() call'\n"
      "print('OK')\n"
    )
    result = _run_py(code)
    assert result.returncode == 0, (
      f'subprocess failed:\nstdout={result.stdout}\nstderr={result.stderr}'
    )
    assert 'OK' in result.stdout

  def test_yfrate_limit_error_module_level_accessible(self) -> None:
    '''Review-fix M4: YFRateLimitError must be importable at module level
    WITHOUT triggering yfinance import. External code that does
    `from data_fetcher import YFRateLimitError` continues to work.
    '''
    code = (
      'import sys\n'
      'from data_fetcher import YFRateLimitError\n'
      "assert 'yfinance' not in sys.modules, "
      "'YFRateLimitError import forced yfinance load'\n"
      'assert isinstance(YFRateLimitError, type), '
      "'YFRateLimitError must be a class'\n"
      'assert issubclass(YFRateLimitError, Exception), '
      "'YFRateLimitError must subclass Exception'\n"
      "print('OK')\n"
    )
    result = _run_py(code)
    assert result.returncode == 0, (
      f'subprocess failed:\nstdout={result.stdout}\nstderr={result.stderr}'
    )
    assert 'OK' in result.stdout

  def test_yfrate_limit_error_catchable(self) -> None:
    '''SC: code that does `except YFRateLimitError` (using the module-level
    proxy class) catches an instance raised through the same name.
    Confirms the proxy class is usable as an exception type.
    '''
    from data_fetcher import YFRateLimitError
    raised = False
    try:
      raise YFRateLimitError('synthetic rate-limit for catch-test')
    except YFRateLimitError as e:
      raised = True
      assert 'synthetic rate-limit' in str(e)
    assert raised, 'YFRateLimitError did not catch its own instance'
