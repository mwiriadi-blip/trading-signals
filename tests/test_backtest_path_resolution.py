"""Phase 29-01 — OPS-02 regression: backtest path constants are CWD-invariant.

Runs an import probe twice — once from project root, once from /tmp — and asserts
stdout is byte-identical between runs.  Proves that Path(__file__).resolve().parents[N]
anchors defeat the old CWD-relative Path('.planning/backtests') bug.

D-16 (29-CONTEXT.md): subprocess-level CWD-invariance test per ROADMAP SC-4.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Resolve project root relative to this test file: tests/ is one level below root
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Import probe: print the 3 resolved paths to stdout (one per line)
_PROBE = (
  'from backtest.cli import _BACKTEST_DIR; '
  'from backtest.data_fetcher import _CACHE_DIR_DEFAULT; '
  'from web.routes.backtest import _BACKTEST_DIR as W; '
  'print(_BACKTEST_DIR); print(_CACHE_DIR_DEFAULT); print(W)'
)


class TestBacktestPathCwdInvariance:
  """Subprocess-level proof that path constants do not depend on caller CWD."""

  def test_paths_identical_from_tmp_and_project_root(self) -> None:
    probe_cmd = [sys.executable, '-c', _PROBE]

    # Ensure project root is on PYTHONPATH so backtest/web modules are importable
    # regardless of which CWD is active.  This is the real-world analog of
    # running `python -m backtest` from a non-project directory with PYTHONPATH set.
    env_with_path = {
      **os.environ,
      'PYTHONPATH': str(_PROJECT_ROOT),
    }

    result_root = subprocess.run(
      probe_cmd,
      cwd=str(_PROJECT_ROOT),
      capture_output=True,
      text=True,
      timeout=60,
      env=env_with_path,
    )
    assert result_root.returncode == 0, (
      f'Probe from project root failed:\n{result_root.stderr}'
    )

    result_tmp = subprocess.run(
      probe_cmd,
      cwd='/tmp',
      capture_output=True,
      text=True,
      timeout=60,
      env=env_with_path,
    )
    assert result_tmp.returncode == 0, (
      f'Probe from /tmp failed:\n{result_tmp.stderr}'
    )

    # Byte-identical stdout between the two CWDs
    assert result_root.stdout == result_tmp.stdout, (
      f'Path outputs differ between CWDs:\n'
      f'  project root: {result_root.stdout!r}\n'
      f'  /tmp:         {result_tmp.stdout!r}'
    )

    # Every resolved line is an absolute path
    lines = result_root.stdout.strip().splitlines()
    assert len(lines) == 3, f'Expected 3 path lines, got: {lines!r}'
    for line in lines:
      assert Path(line).is_absolute(), f'Path not absolute: {line!r}'

    # Lines end with expected suffixes
    expected_suffixes = [
      '.planning/backtests',
      '.planning/backtests/data',
      '.planning/backtests',
    ]
    for line, suffix in zip(lines, expected_suffixes):
      assert line.endswith(suffix), (
        f'Expected path ending in {suffix!r}, got {line!r}'
      )
