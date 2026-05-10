---
phase: 29
plan: 01
plan_id: 29-01-OPS-02-BACKTESTS-PATH-FIX
subsystem: backtest
tags: [path-fix, backtest, ops, cwd-invariance]
dependency_graph:
  requires: []
  provides: [OPS-02]
  affects: [backtest/cli.py, backtest/data_fetcher.py, web/routes/backtest.py, tests/test_backtest_path_resolution.py]
tech_stack:
  added: []
  patterns: [Path(__file__).resolve().parents[N] module-level anchor]
key_files:
  modified:
    - backtest/cli.py
    - backtest/data_fetcher.py
    - web/routes/backtest.py
  created:
    - tests/test_backtest_path_resolution.py
decisions:
  - "D-14/D-15: module-level Path(__file__).resolve().parents[N] in each caller — no shared paths.py helper"
  - "D-16: subprocess-level CWD-invariance test with PYTHONPATH set to project root"
metrics:
  duration: ~6min
  completed: 2026-05-10T08:03:00Z
  tasks: 2
  files: 4
---

# Phase 29 Plan 01: OPS-02 Backtests Path Fix Summary

**One-liner:** Replace CWD-relative `.planning/backtests` Path constants in 3 modules with `Path(__file__).resolve().parents[N]` anchors; proves CWD-invariance via subprocess regression test.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Anchor 3 backtest path constants to project root | 53d797d | backtest/cli.py, backtest/data_fetcher.py, web/routes/backtest.py |
| 2 | Subprocess regression test — CLI from /tmp and project root produces identical output paths | cf14e32 | tests/test_backtest_path_resolution.py |

## What Was Done

### Task 1

Three CWD-relative path constants replaced with module-anchored absolutes:

- `backtest/cli.py:46` — `_PROJECT_ROOT = Path(__file__).resolve().parents[1]` + `_BACKTEST_DIR = _PROJECT_ROOT / '.planning' / 'backtests'`
- `backtest/data_fetcher.py:24` — `_PROJECT_ROOT = Path(__file__).resolve().parents[1]` + `_CACHE_DIR_DEFAULT = _PROJECT_ROOT / '.planning' / 'backtests' / 'data'`
- `web/routes/backtest.py:45` — `_PROJECT_ROOT = Path(__file__).resolve().parents[2]` + `_BACKTEST_DIR = _PROJECT_ROOT / '.planning' / 'backtests'`

`parents[1]` is correct for both `backtest/` modules (one level below project root). `parents[2]` is correct for `web/routes/backtest.py` (two levels below project root). All three resolve to `/Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.planning/backtests` and are byte-identical between CLI and route module.

### Task 2

Created `tests/test_backtest_path_resolution.py` with `TestBacktestPathCwdInvariance.test_paths_identical_from_tmp_and_project_root`. The test:
1. Runs an import probe twice: `cwd=PROJECT_ROOT` and `cwd=/tmp`
2. Both invocations use `PYTHONPATH=PROJECT_ROOT` so modules are importable from `/tmp`
3. Asserts stdout (3 path lines) is byte-identical between runs
4. Asserts every line is an absolute path ending in `.planning/backtests` or `.planning/backtests/data`

## Verification

All acceptance criteria passed:

```
cli.py OK
data_fetcher.py OK
web/routes/backtest.py OK
No CWD-relative leftovers — OK
cli _BACKTEST_DIR: /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.planning/backtests
data_fetcher path: /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.planning/backtests/data
web/routes/backtest path: /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals/.planning/backtests
OK  (assert _BACKTEST_DIR == W passed)
pytest tests/test_backtest_path_resolution.py -x -q: 1 passed
Full suite: 2029 passed, 2 pre-existing failures (dashboard golden snapshot — unrelated to this plan)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PYTHONPATH required for /tmp subprocess probe**

- **Found during:** Task 2
- **Issue:** The subprocess probe invoked from `cwd='/tmp'` raised `ModuleNotFoundError: No module named 'backtest'` because Python's import machinery only searches `sys.path`, which does not include the project root when CWD is `/tmp`.
- **Fix:** Set `PYTHONPATH=str(_PROJECT_ROOT)` in the subprocess env for both invocations. This is the real-world analog of `python -m backtest` with `PYTHONPATH` set — the modules are importable from any CWD.
- **Files modified:** `tests/test_backtest_path_resolution.py`
- **Commit:** cf14e32

## Known Stubs

None.

## Threat Flags

None. The `Path(__file__).resolve()` pattern leaks the repo's absolute path in logs, but T-29-01-02 disposition is `accept` (single-operator system; absolute path already appears in journalctl; no PII).

## Self-Check: PASSED

- [x] `backtest/cli.py` exists and contains `Path(__file__).resolve().parents`
- [x] `backtest/data_fetcher.py` exists and contains `Path(__file__).resolve().parents`
- [x] `web/routes/backtest.py` exists and contains `Path(__file__).resolve().parents`
- [x] `tests/test_backtest_path_resolution.py` exists with `subprocess.run` and `/tmp` and `TestBacktestPathCwdInvariance`
- [x] Task 1 commit 53d797d exists in git log
- [x] Task 2 commit cf14e32 exists in git log
- [x] ROADMAP SC-4 satisfied: CWD-invariance proven by subprocess regression test
