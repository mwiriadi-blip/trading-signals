---
phase: 23
plan: 02
subsystem: backtest-data-fetcher
tags: [data-fetch, parquet, cache, hex-boundary, yfinance, BACKTEST-01]
requires: [23-01]
provides:
  - backtest.data_fetcher.fetch_ohlcv (yfinance + 24h parquet cache)
  - backtest.data_fetcher.DataFetchError
  - backtest.data_fetcher.ShortFrameError (CONTEXT D-17 bail)
  - backtest.data_fetcher._cache_path / _is_cache_fresh helpers
  - 4 test classes (10 tests) covering cache hit/miss/refresh/parquet/short-bail
affects:
  - backtest/data_fetcher.py
  - tests/test_backtest_data_fetcher.py
tech-stack:
  added: []
  patterns:
    - parquet cache with mtime-based 24h staleness (CONTEXT D-01)
    - cache-then-network adapter (cache check → yfinance → validate → write)
    - TZ-aware DatetimeIndex round-trip via pyarrow engine (RESEARCH §Pitfall 8)
    - monkeypatch backtest.data_fetcher.yf.Ticker for test isolation (no network)
    - synthetic 5y+ frame fixture matched to production min_years threshold
key-files:
  created: []
  modified:
    - backtest/data_fetcher.py
    - tests/test_backtest_data_fetcher.py
  also_created:
    - .planning/phases/23-five-year-backtest-validation-gate/deferred-items.md
decisions:
  - Symbol kept verbatim in cache filename (no sanitisation) — POSIX-safe; matches D-01 example.
  - ShortFrameError subclasses ValueError (not Exception) — operator can catch as ValueError if needed.
  - DataFetchError uses broad `except Exception` for the yfinance call; narrower than no try (which would crash the CLI), broader than retry-list (acceptable since retries are not in scope for this plan).
  - Test fixture widens synthetic frame ±60d each side around the requested window so calendar span comfortably exceeds 5y regardless of operator window.
metrics:
  duration: ~6 minutes
  completed: 2026-05-01
  tasks: 2
  files: 2 modified, 1 created (deferred-items.md)
  commits: 2
---

# Phase 23 Plan 02: Wave 1A — backtest/data_fetcher.py (yfinance + parquet cache) Summary

Implements `backtest.data_fetcher.fetch_ohlcv` — the ONE I/O exception in the
backtest hex per CONTEXT D-09. Replaces the Wave 0 `NotImplementedError` stub
with a yfinance fetcher backed by a 24h parquet cache at
`.planning/backtests/data/<symbol>-<start>-<end>.parquet`. Decouples yfinance
latency from per-run cost: subsequent backtests within 24h are sub-second on
the data layer. Adds 4 test classes (10 tests) covering cache hit/miss,
parquet round-trip, refresh flag, and `<5y` bail.

## Tasks Completed

| Task | Name | Commit |
|------|------|--------|
| 1 | Implement `backtest/data_fetcher.py` (cache + fetch + bail) | 40e5a6c |
| 2 | Implement `tests/test_backtest_data_fetcher.py` (4 test classes) | 16792b9 |

## Verification Results

### 1. Module imports + cache filename contract
```
$ .venv/bin/python -c "from backtest.data_fetcher import fetch_ohlcv, \
  DataFetchError, ShortFrameError, _cache_path, _is_cache_fresh; \
  from pathlib import Path; \
  assert _cache_path('^AXJO', '2021-05-01', '2026-05-01', Path('/tmp')).name \
    == '^AXJO-2021-05-01-2026-05-01.parquet'; print('ok')"
ok
```

### 2. Acceptance-criteria grep checks (all from plan §Task 1)
```
$ grep -c '^def fetch_ohlcv'           backtest/data_fetcher.py   # 1
$ grep -c '^class ShortFrameError'     backtest/data_fetcher.py   # 1
$ grep -c '^class DataFetchError'      backtest/data_fetcher.py   # 1
$ grep -c '_REQUIRED_COLUMNS'          backtest/data_fetcher.py   # 2
$ grep -c "engine='pyarrow'"           backtest/data_fetcher.py   # 2  (write + read)
$ grep -c '\[Backtest\]'               backtest/data_fetcher.py   # 6
$ grep -cE '^import state_manager|^from state_manager|^import notifier|\
^from notifier|^import dashboard|^from dashboard|^import main' \
                                       backtest/data_fetcher.py   # 0
```

### 3. AUDUSD cache path
```
$ .venv/bin/python -c "from backtest.data_fetcher import _cache_path; \
  from pathlib import Path; \
  assert str(_cache_path('AUDUSD=X', '2021-05-01', '2026-05-01', \
    Path('.planning/backtests/data'))).endswith(\
    'AUDUSD=X-2021-05-01-2026-05-01.parquet')"
(no output → success)
```

### 4. Test suite
```
$ .venv/bin/pytest tests/test_backtest_data_fetcher.py -x -q
..........                                                               [100%]
10 passed in 13.49s
```

Per-class breakdown:
- `TestCacheHitMiss` — 3 tests (cache miss writes parquet, cache hit skips
  yfinance, stale cache re-fetches)
- `TestParquetRoundTrip` — 2 tests (TZ-aware index preserved, OHLCV columns
  present)
- `TestRefreshFlag` — 1 test (refresh=True bypasses fresh cache)
- `TestShortDataBail` — 2 tests (ShortFrameError on <5y, DataFetchError on
  empty frame)
- `TestCacheFilename` — 2 tests (^AXJO and AUDUSD=X filename formats)

All 10 monkeypatch `backtest.data_fetcher.yf.Ticker`; zero real network calls.

### 5. AST hex-boundary guard regression
```
$ .venv/bin/pytest tests/test_signal_engine.py::TestDeterminism -x -q
.......................................................                 [100%]
55 passed in 2.54s
```

`backtest/data_fetcher.py` is the documented I/O exception per D-09 — explicitly
excluded from `_BACKTEST_PATHS_PURE` (tests/test_signal_engine.py:600). The
guard against `pyarrow` leakage into pure modules continues to pass.

### 6. Combined backtest + AST regression suite
```
$ .venv/bin/pytest tests/test_backtest_data_fetcher.py \
                  tests/test_signal_engine.py::TestDeterminism -q
.................................................................        [100%]
65 passed in 4.98s
```

## Threats Addressed

| Threat ID | Mitigation status |
|-----------|-------------------|
| T-23-cache-tamper | Mitigated — parquet binary columnar format (no eval / code paths on read); `_REQUIRED_COLUMNS` validation runs after every yfinance fetch (cache reads inherit the validation indirectly via the validate-on-write contract); `--refresh` recovery path is operator-driven. Wave 0 already added `.planning/backtests/data/` to `.gitignore`. |
| T-23-pyarrow | Mitigated — Wave 0 pinned `pyarrow==24.0.0`; this plan uses the engine via pandas without further attack-surface expansion. AST guard in `tests/test_signal_engine.py::test_backtest_pure_no_pyarrow_import` blocks `pyarrow` from leaking into the pure-math siblings (`simulator/metrics/render`). |

## Deviations from Plan

None — plan executed exactly as written. Both tasks completed in order, all
plan acceptance criteria met, all 10 new tests pass, full TestDeterminism
hex-boundary suite remains green.

## Auth Gates

None — fetch path uses public yfinance HTTPS with no credentials.

## Threat Flags

None — this plan introduces no new security surface beyond what was documented
in the plan's `<threat_model>` (yfinance HTTPS boundary already existed in
top-level `data_fetcher.py`; the parquet cache is operator-local, gitignored).

## Deferred Issues

Pre-existing `tests/test_nginx_signals_conf.py::TestNginxConfStructure::test_listen_443_ssl`
failure persists at the worktree base commit (verified via `git stash` baseline).
Out of scope for plan 23-02 (touches nginx deploy config, not backtest module).
Logged to
`.planning/phases/23-five-year-backtest-validation-gate/deferred-items.md`
for the next maintenance pass.

## Self-Check: PASSED

Files verified present:

```
backtest/data_fetcher.py                            FOUND  (full impl, 137 lines)
tests/test_backtest_data_fetcher.py                 FOUND  (4 test classes + 1 filename class, 10 tests)
.planning/phases/23-five-year-backtest-validation-gate/deferred-items.md  FOUND
```

Commits verified in `git log`:

```
40e5a6c  FOUND  feat(23-02): implement backtest/data_fetcher.fetch_ohlcv with parquet cache
16792b9  FOUND  test(23-02): add 4 test classes for backtest/data_fetcher
```

Wave 1B (plan 23-03 simulator) and Wave 1C (plan 23-04 metrics) are now
unblocked on the data layer — `fetch_ohlcv` delivers TZ-aware OHLCV frames
ready for `signal_engine.compute_indicators` consumption per CONTEXT D-10.
