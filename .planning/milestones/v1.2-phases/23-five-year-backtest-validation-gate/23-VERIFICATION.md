---
phase: 23-five-year-backtest-validation-gate
verified: 2026-05-01T12:52:47Z
status: human_needed
score: 7/7 must-haves verified (automated); 2 items require human testing
overrides_applied: 0
human_verification:
  - test: "Run `python -m backtest --years 5` on the deployed droplet (or locally with live yfinance)"
    expected: "Completes in <60s, prints [Backtest] PASS or FAIL summary, writes .planning/backtests/v1.2.0-<timestamp>.json containing metadata + metrics + equity_curve + trades per D-05 schema"
    why_human: "Requires live yfinance network call and actual OHLCV data; cannot verify without I/O in a static code check. Also validates real 5y data coverage for both ^AXJO and AUDUSD=X."
  - test: "Open /backtest in a browser with a valid session cookie after running at least one CLI backtest"
    expected: "Page renders three tabs (Combined / SPI 200 / AUD/USD) with Chart.js equity curve, metrics table, pass/fail badge, and the operator override form. POST override form runs a new simulation and redirects back to /backtest showing the new run."
    why_human: "Visual layout, tab switching behavior, Chart.js canvas rendering, and round-trip form POST require browser testing. Tests cover route responses but not rendered visual output."
---

# Phase 23: Five-Year Backtest Validation Gate — Verification Report

**Phase Goal:** Five-year backtest validation gate — bar-by-bar replay engine reusing live signal+sizing engines, with metrics, HTML report, CLI, and web routes.
**Verified:** 2026-05-01T12:52:47Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | backtest/ package exists with all 7 module skeletons importable | ✓ VERIFIED | `python -c "import backtest; from backtest import cli, simulator, metrics, render, data_fetcher; ..."; print('ok')` succeeds |
| 2 | Simulator reuses signal_engine.compute_indicators + sizing_engine.step verbatim (BACKTEST-01) | ✓ VERIFIED | `backtest/simulator.py:25-26`: `from signal_engine import ... compute_indicators` and `from sizing_engine import step`; no re-implementation present |
| 3 | compute_metrics returns all 8 fields including sharpe_annualized and strict pass criterion (BACKTEST-02) | ✓ VERIFIED | Behavioral spot-check: all fields present; `>100%` returns True, `==100%` returns False (D-16 strict) |
| 4 | render_report produces three tabs (combined/spi200/audusd) + pass/fail badge + override form (BACKTEST-03) | ✓ VERIFIED | `render_report(golden_report)` returns 7762-char HTML containing all three tab identifiers, pass/fail badge, and /backtest/run form |
| 5 | CLI `python -m backtest` with argparse surface per D-11; exit code 0=PASS / 1=FAIL (BACKTEST-04) | ✓ VERIFIED | `_build_parser()` returns parser with all 7 args per D-11; `run_backtest()` returns `(report, path, exit_code)` where exit_code gates on `cumulative_return_pct > 100.0` |
| 6 | Web routes GET /backtest + POST /backtest/run mounted and auth-gated by Phase 16.1 | ✓ VERIFIED | `web/app.py:49,162` mounts routes; TestCookieAuth (3 tests) all pass: no-cookie GET→302/401, no-cookie POST→401 |
| 7 | Hex-boundary preserved: simulator/metrics/render import no forbidden modules; pyarrow isolated to data_fetcher | ✓ VERIFIED | AST guard tests (4 parametrized) all pass; grep confirms no forbidden imports in simulator/metrics/render; data_fetcher is the sole pyarrow user |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backtest/__init__.py` | BACKTEST_INITIAL_ACCOUNT_AUD constant | ✓ VERIFIED | 6 constants present including BACKTEST_INITIAL_ACCOUNT_AUD=10_000.0 |
| `backtest/data_fetcher.py` | fetch_ohlcv + ShortFrameError + DataFetchError | ✓ VERIFIED | All three exported; parquet cache with engine='pyarrow' confirmed |
| `backtest/simulator.py` | simulate() + SimResult | ✓ VERIFIED | 160+ LOC implemented; imports signal_engine + sizing_engine directly |
| `backtest/metrics.py` | compute_metrics() with 8 fields + pass criterion | ✓ VERIFIED | Dual sharpe (D-19), strict pass (D-16), pandas cummax idiom |
| `backtest/render.py` | render_report/history/run_form; Chart.js SRI present | ✓ VERIFIED | 382 LOC; _CHARTJS_URL + _CHARTJS_SRI constants present; json injection defence (_payload helper) |
| `backtest/cli.py` | main() + run_backtest() + _build_parser() | ✓ VERIFIED | All three exported; STRATEGY_VERSION read fresh inside run_backtest (G-45 correct) |
| `backtest/__main__.py` | python -m backtest dispatch | ✓ VERIFIED | Dispatches to backtest.cli.main() |
| `web/routes/backtest.py` | 4 routes + path-traversal + input validation | ✓ VERIFIED | 224 LOC; _resolve_safe_backtest_path two-layer defence; 303 redirect on POST |
| `tests/fixtures/backtest/golden_report.json` | Full D-05 schema | ✓ VERIFIED | metadata + metrics (combined/SPI200/AUDUSD) + equity_curve + trades; dual sharpe; valid exit_reason values |
| `requirements.txt` | pyarrow==24.0.0 | ✓ VERIFIED | `grep -c '^pyarrow==24.0.0$'` returns 1 |
| `.gitignore` | .planning/backtests/data/ | ✓ VERIFIED | `grep -c '^\.planning/backtests/data/$'` returns 1 |
| `tests/test_signal_engine.py` | BACKTEST_PATHS_PURE + new AST guard tests | ✓ VERIFIED | BACKTEST_SIMULATOR_PATH, BACKTEST_METRICS_PATH, BACKTEST_RENDER_PATH defined; test_backtest_render_no_forbidden_imports + test_backtest_pure_no_pyarrow_import both present and passing |
| All 6 test files | 99 tests passing | ✓ VERIFIED | 99 passed (29 render + 13 CLI + 21 web + 4 data_fetcher + 7 simulator + 25 metrics); 18 non-blocking deprecation warnings |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backtest/simulator.py` | `signal_engine.compute_indicators + sizing_engine.step` | direct imports (D-10) | ✓ WIRED | Lines 25-26 import both; step() called in simulate() loop |
| `backtest/data_fetcher.py` | pyarrow | `df.to_parquet/read_parquet(engine='pyarrow')` | ✓ WIRED | Lines 128, 136 confirmed |
| `backtest/cli.py` | data_fetcher + simulator + metrics | direct function calls | ✓ WIRED | Lines 37-39: all three imported; run_backtest() orchestrates all three |
| `web/routes/backtest.py` | `backtest.cli.run_backtest + backtest.render.*` | direct function calls | ✓ WIRED | Lines 39-41: imports confirmed; POST handler calls run_backtest; GET handler calls render_* |
| `web/app.py` | `web/routes/backtest.py` | `backtest_route.register(application)` | ✓ WIRED | Lines 49, 162 confirmed |
| `tests/test_signal_engine.py` | `backtest/simulator.py + metrics.py + render.py` | AST guard parametrize | ✓ WIRED | 7 parametrized tests pass in TestDeterminism::test_forbidden_imports_absent |
| `backtest/cli.py` | `system_params.STRATEGY_VERSION` | fresh attribute access inside run_backtest() | ✓ WIRED | Line 172: `strategy_version = system_params.STRATEGY_VERSION` inside function body (not kwarg default) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `backtest/render.py::render_report` | `report` dict | Caller passes D-05 dict from json.load or run_backtest | ✓ (dict contains real metrics + trades + equity_curve) | ✓ FLOWING |
| `web/routes/backtest.py::get_backtest` | `report` dict | `json.loads(path.read_text())` from .planning/backtests/*.json | ✓ (reads actual persisted files; empty-state on no files) | ✓ FLOWING |
| `web/routes/backtest.py::post_backtest_run` | `(report, path, exit_code)` | `run_backtest(RunArgs(...))` orchestrates full data_fetcher→simulator→metrics pipeline | ✓ (live computation with real or cached OHLCV) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| backtest package importable | `python -c "import backtest; from backtest import ..."` | ok | ✓ PASS |
| compute_metrics returns all 8 D-05 fields | Inline Python spot-check | All fields present, correct types | ✓ PASS |
| D-16 strict pass criterion | `>100.0` → True; `==100.0` → False | Both correct | ✓ PASS |
| render_report produces 3 tabs + badge + form | Inline Python against golden_report | 7762 chars with all required elements | ✓ PASS |
| argparse surface matches D-11 | `_build_parser().parse_args(...)` | All 7 args parsed correctly | ✓ PASS |
| Cookie auth: no-cookie → 302/401 | TestCookieAuth (3 tests) | 3 passed | ✓ PASS |
| Path-traversal guard | TestPathTraversal (5 tests) | 5 passed | ✓ PASS |
| Full backtest + AST test suite | 154 tests (backtest + TestDeterminism) | 154 passed, 0 failed | ✓ PASS |
| python -m backtest with live data | Requires live yfinance + network | Cannot run in static check | ? SKIP (human needed) |
| /backtest visual rendering in browser | Requires browser + session + run JSON | Cannot verify programmatically | ? SKIP (human needed) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| BACKTEST-01 | 23-02, 23-03 | backtest/ module, hex-boundary, bar-by-bar replay using live engines | ✓ SATISFIED | simulator.py imports signal_engine + sizing_engine; hex-boundary AST guard enforced; data_fetcher is documented I/O exception |
| BACKTEST-02 | 23-04 | Both instruments, equity curve, 6 metrics + strategy_version | ✓ SATISFIED | compute_metrics returns all required fields including sharpe_annualized (D-19); STRATEGY_VERSION read from system_params inside run_backtest |
| BACKTEST-03 | 23-05, 23-07 | /backtest route renders report with chart, metrics, pass/fail badge | ✓ SATISFIED | render_report produces 3-tab Chart.js layout; web route returns HTML; TestGetBacktest passes |
| BACKTEST-04 | 23-06, 23-07 | CLI re-runnable, JSON persisted, fail-loud badge | ✓ SATISFIED | python -m backtest entry wired; JSON written to .planning/backtests/<sv>-<ts>.json; exit 0=PASS/1=FAIL |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None | — | — | — |

No NotImplementedError stubs, TODO/FIXME comments, hardcoded empty returns, or forbidden imports found in any implemented module.

### Human Verification Required

#### 1. End-to-End CLI Run with Live yfinance Data

**Test:** Run `python -m backtest --years 5` (with network access and yfinance available)
**Expected:** Completes in <60s; prints `[Backtest] Fetching SPI200 ...` and `[Backtest] Fetching AUDUSD ...` lines; prints combined summary with cum_return / sharpe / max_dd / win_rate / trades; prints `[Backtest] PASS` or `[Backtest] FAIL`; writes `.planning/backtests/v1.2.0-<timestamp>.json` with `metadata`, `metrics`, `equity_curve`, `trades` per D-05 schema.
**Why human:** Requires live yfinance network call and 5 years of real OHLCV data for ^AXJO and AUDUSD=X. Static code analysis confirms all wiring is correct but cannot execute the actual data fetch.

#### 2. Web Route Browser Smoke Test

**Test:** With a running server and a valid session cookie, navigate to `/backtest` after at least one CLI run exists in `.planning/backtests/`.
**Expected:** Page shows three Chart.js tabs (Combined / SPI 200 / AUD/USD) each with an equity curve chart, metrics row, and pass/fail badge. Override form appears at top. Clicking a tab switches the active panel. Submitting the override form runs a new simulation and redirects back to `/backtest` showing the new run.
**Why human:** Visual layout, tab-switching JS behavior, Chart.js canvas rendering, and the POST round-trip require browser testing. Route tests (TestGetBacktest, TestPostRun) confirm HTTP-level correctness but not visual output.

### Gaps Summary

No automated blockers found. All 7 observable truths verified, all 99 backtest tests pass, all key links wired. Phase goal is achieved at the code level. Two human verification items remain for live integration and visual smoke testing — these are standard pre-deployment checks, not code defects.

---

_Verified: 2026-05-01T12:52:47Z_
_Verifier: Claude (gsd-verifier)_
