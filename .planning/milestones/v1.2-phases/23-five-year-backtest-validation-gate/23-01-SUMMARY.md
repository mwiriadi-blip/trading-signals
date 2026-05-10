---
phase: 23
plan: 01
subsystem: backtest-scaffolding
tags: [scaffolding, hex-boundary, ast-guard, pyarrow, fixture]
requires: []
provides:
  - backtest/__init__.py constants module
  - backtest/{cli,simulator,metrics,render,data_fetcher,__main__}.py skeletons
  - web/routes/backtest.py + mount in web/app.py
  - extended AST hex-boundary guard (BACKTEST_PATHS_PURE)
  - tests/fixtures/backtest/golden_report.json (D-05 schema)
  - 6 test file skeletons (29 skipped tests collected)
  - pyarrow==24.0.0 pinned in requirements.txt + .venv
  - .planning/backtests/data/ git-ignored
affects:
  - requirements.txt
  - .gitignore
  - web/app.py
  - tests/test_signal_engine.py
tech-stack:
  added: [pyarrow==24.0.0]
  patterns:
    - hex-pure constants module (mirrors system_params.py)
    - I/O exception documented in module docstring (mirrors data_fetcher.py:1-25)
    - Chart.js URL+SRI duplicated to avoid dashboard import (D-07)
    - register() factory pattern (mirrors paper_trades_route)
    - AST guard parametrize extension (mirrors Phase 19/20 pnl/alert pattern)
key-files:
  created:
    - backtest/__init__.py
    - backtest/__main__.py
    - backtest/data_fetcher.py
    - backtest/simulator.py
    - backtest/metrics.py
    - backtest/render.py
    - backtest/cli.py
    - web/routes/backtest.py
    - tests/test_backtest_data_fetcher.py
    - tests/test_backtest_simulator.py
    - tests/test_backtest_metrics.py
    - tests/test_backtest_render.py
    - tests/test_backtest_cli.py
    - tests/test_web_backtest.py
    - tests/fixtures/backtest/golden_report.json
  modified:
    - requirements.txt
    - .gitignore
    - web/app.py
    - tests/test_signal_engine.py
decisions: []
metrics:
  duration: ~10 minutes
  completed: 2026-05-01
  tasks: 6
  files: 19 (15 created, 4 modified)
  commits: 6
---

# Phase 23 Plan 01: Wave 0 — Scaffolding, pyarrow pin, AST guard extension Summary

Pure scaffolding plan: pin pyarrow, create the `backtest/` package + 7 module skeletons, mount `/backtest` web routes, hand-author the D-05 golden report fixture, extend the AST hex-boundary guard to catch forbidden imports + pyarrow leakage in `backtest/{simulator,metrics,render}.py`, and create 6 empty pytest test file skeletons (29 named classes, all skipping) to back the VALIDATION.md verification map. Wave 1+ plans fill in the implementations.

## Tasks Completed

| Task | Name | Commit |
|------|------|--------|
| 1 | Pin pyarrow + .gitignore cache dir | 7cac18e |
| 2 | Create backtest/ package skeleton (7 files) | 23e3cc5 |
| 3 | Create web/routes/backtest.py skeleton + mount in web/app.py | 5f1becb |
| 4 | Extend AST guard in tests/test_signal_engine.py for BACKTEST_PATHS_PURE | 8169e40 |
| 5 | Hand-author tests/fixtures/backtest/golden_report.json | d28dc95 |
| 6 | Create 6 empty test file skeletons | b95bc1f |

## Verification Results

### 1. pyarrow installed and pinned
```
$ pip show pyarrow | grep -E '^Version: 24\.0\.0$'
Version: 24.0.0
$ grep -c '^pyarrow==24.0.0$' requirements.txt
1
```

### 2. backtest/ package import graph
```
$ python -c "import backtest; from backtest import cli, simulator, metrics, render, data_fetcher; from backtest.cli import main; from backtest.simulator import simulate; from backtest.metrics import compute_metrics; from backtest.render import render_report, render_history, render_run_form; from backtest.data_fetcher import fetch_ohlcv; print('ok')"
ok
$ python -c "from backtest import BACKTEST_INITIAL_ACCOUNT_AUD; assert BACKTEST_INITIAL_ACCOUNT_AUD == 10_000.0; print('ok')"
ok
```

### 3. Web routes mounted in FastAPI
```
$ python -c "from web.app import create_app; app=create_app(); paths=sorted({r.path for r in app.routes}); assert '/backtest' in paths and '/backtest/run' in paths; print('ok')"
ok
```

### 4. AST guard extension (TestDeterminism class)
- `test_forbidden_imports_absent`: now parametrized over **7** paths (was 5) — adds `BACKTEST_SIMULATOR_PATH`, `BACKTEST_METRICS_PATH`
- `test_backtest_render_no_forbidden_imports`: NEW — render.py allowlist excludes json from forbidden set
- `test_backtest_pure_no_pyarrow_import`: NEW — parametrized × 3 (simulator/metrics/render) blocks pyarrow leakage
- Total: 11 new/extended assertions; full TestDeterminism class: 55 passed in 1.92s

```
$ pytest tests/test_signal_engine.py::TestDeterminism -x -q
55 passed in 1.92s
```

### 5. Golden fixture schema validation
```
$ python -c "import json, pathlib; r=json.loads(pathlib.Path('tests/fixtures/backtest/golden_report.json').read_text()); assert set(r) == {'metadata','metrics','equity_curve','trades'}; assert set(r['metrics']) == {'combined','SPI200','AUDUSD'}; assert r['metrics']['combined']['pass'] is True; assert r['metrics']['combined']['cumulative_return_pct'] > 100.0; assert len(r['trades']) == 2; assert all(t['exit_reason'] in {'flat_signal','signal_reversal','trailing_stop','adx_drop','manual_stop'} for t in r['trades']); print('ok')"
ok
$ wc -c tests/fixtures/backtest/golden_report.json
2413 tests/fixtures/backtest/golden_report.json
```
- Both `sharpe_daily` AND `sharpe_annualized` per metric block (planner D-19)
- exit_reason values from planner D-20 mapping (`signal_reversal`, `trailing_stop`)
- 2413 bytes (within 1500-6000 target)

### 6. Test skeleton collection
```
$ pytest tests/test_backtest_*.py tests/test_web_backtest.py -q
29 skipped in 0.08s
```

29 named test classes across 6 files, all skipping with Wave 1+ marker:

| File | Classes |
|------|---------|
| `tests/test_backtest_data_fetcher.py` | TestCacheHitMiss, TestParquetRoundTrip, TestRefreshFlag, TestShortDataBail |
| `tests/test_backtest_simulator.py` | TestDeterminism, TestCostModel, TestExitReasons, TestNanSafety |
| `tests/test_backtest_metrics.py` | TestCumulativeReturn, TestSharpe, TestMaxDrawdown, TestWinRateExpectancy, TestPassCriterion |
| `tests/test_backtest_render.py` | TestRenderReport, TestChartJsSri, TestRenderHistory, TestRenderRunForm, TestEmptyState, TestJsonInjectionDefence |
| `tests/test_backtest_cli.py` | TestArgparse, TestJsonSchema, TestExitCode, TestLogFormat, TestStrategyVersionTagging |
| `tests/test_web_backtest.py` | TestGetBacktest, TestPathTraversal, TestPostRun, TestCookieAuth, TestHistoryView |

### 7. Cache dir git-ignored
```
$ grep -c '^\.planning/backtests/data/$' .gitignore
1
```

## Hex-Boundary Map Locked

| Module | Tier | AST list | Forbidden adds |
|--------|------|----------|----------------|
| `backtest/__init__.py` | constants | (none — no imports beyond stdlib) | n/a |
| `backtest/__main__.py` | adapter | (none) | n/a |
| `backtest/data_fetcher.py` | I/O exception | **EXCLUDED** per D-09 | yfinance + pyarrow allowed |
| `backtest/simulator.py` | pure-math | `_HEX_PATHS_ALL` + `_BACKTEST_PATHS_PURE` | FORBIDDEN_MODULES + pyarrow |
| `backtest/metrics.py` | pure-math | `_HEX_PATHS_ALL` + `_BACKTEST_PATHS_PURE` | FORBIDDEN_MODULES + pyarrow |
| `backtest/render.py` | pure-render | `_BACKTEST_PATHS_PURE` only (NOT _HEX_PATHS_ALL) | FORBIDDEN_MODULES − {json} + pyarrow |
| `backtest/cli.py` | adapter | (none) | n/a |
| `web/routes/backtest.py` | adapter | (none) | n/a |

## Threats Addressed

| Threat ID | Mitigation status |
|-----------|-------------------|
| T-23-pyarrow | Mitigated — exact `pyarrow==24.0.0` pin in requirements.txt; install verified via `pip show pyarrow` |
| T-23-cache-tamper | Mitigated — `.planning/backtests/data/` added to .gitignore; parquet binary columnar format (no eval); `--refresh` recovery deferred to Wave 1 Plan 02 implementation |

## Deviations from Plan

None — plan executed exactly as written. All 6 tasks completed in order, all acceptance criteria met, all 7 verification commands return ok / pass.

## Auth Gates

None — Wave 0 is pure scaffolding (no live network calls, no auth surface touched).

## Threat Flags

None — Wave 0 introduces only skeletons (raise NotImplementedError) and a fixture; no new live security surface beyond what was documented in the plan's `<threat_model>`.

## Self-Check: PASSED

Verified all 19 expected files (created + modified):

```
backtest/__init__.py                                FOUND
backtest/__main__.py                                FOUND
backtest/data_fetcher.py                            FOUND
backtest/simulator.py                               FOUND
backtest/metrics.py                                 FOUND
backtest/render.py                                  FOUND
backtest/cli.py                                     FOUND
web/routes/backtest.py                              FOUND
web/app.py (modified)                               FOUND
tests/test_signal_engine.py (modified)              FOUND
tests/test_backtest_data_fetcher.py                 FOUND
tests/test_backtest_simulator.py                    FOUND
tests/test_backtest_metrics.py                      FOUND
tests/test_backtest_render.py                       FOUND
tests/test_backtest_cli.py                          FOUND
tests/test_web_backtest.py                          FOUND
tests/fixtures/backtest/golden_report.json          FOUND
requirements.txt (modified)                         FOUND
.gitignore (modified)                               FOUND
```

Verified all 6 commits exist:

```
7cac18e  FOUND  chore(23-01): pin pyarrow==24.0.0 + gitignore parquet cache
23e3cc5  FOUND  feat(23-01): backtest package skeleton with 7 modules
5f1becb  FOUND  feat(23-01): mount /backtest GET + /backtest/run POST routes
8169e40  FOUND  test(23-01): extend AST hex-boundary guard for backtest pure modules
d28dc95  FOUND  test(23-01): hand-authored golden_report.json fixture per D-05 schema
b95bc1f  FOUND  test(23-01): add 6 backtest test file skeletons (29 skipped)
```

Wave 1 plans (23-02 data_fetcher, 23-03 simulator, 23-04 metrics) and Wave 2 plans (23-05 render, 23-06 cli, 23-07 web routes) are now unblocked — all scaffolds, fixtures, and AST guards are in place.
