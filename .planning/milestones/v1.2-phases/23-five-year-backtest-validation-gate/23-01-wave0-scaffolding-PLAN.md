---
id: 23-01
title: Wave 0 — Scaffolding, pyarrow pin, AST guard extension
phase: 23
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - requirements.txt
  - .gitignore
  - tests/test_signal_engine.py
  - backtest/__init__.py
  - backtest/__main__.py
  - backtest/data_fetcher.py
  - backtest/simulator.py
  - backtest/metrics.py
  - backtest/render.py
  - backtest/cli.py
  - tests/test_backtest_data_fetcher.py
  - tests/test_backtest_simulator.py
  - tests/test_backtest_metrics.py
  - tests/test_backtest_render.py
  - tests/test_backtest_cli.py
  - tests/test_web_backtest.py
  - tests/fixtures/backtest/golden_report.json
  - web/routes/backtest.py
  - web/app.py
requirements: [BACKTEST-01, BACKTEST-02, BACKTEST-03, BACKTEST-04]
threat_refs: [T-23-pyarrow, T-23-cache-tamper]
autonomous: true
gap_closure: false

must_haves:
  truths:
    - "pyarrow==24.0.0 is pinned in requirements.txt and installed in .venv"
    - "backtest/ package exists with all 7 module skeletons importable"
    - "AST guard at tests/test_signal_engine.py extends to walk backtest/simulator.py, backtest/metrics.py, backtest/render.py against forbidden imports"
    - "All 6 test files exist (skeletons, with all-skip behavior)"
    - "Golden report fixture exists at tests/fixtures/backtest/golden_report.json with full D-05 schema"
    - ".planning/backtests/data/ is git-ignored"
  artifacts:
    - path: "requirements.txt"
      provides: "pyarrow==24.0.0 pinned"
      contains: "pyarrow==24.0.0"
    - path: "backtest/__init__.py"
      provides: "BACKTEST_INITIAL_ACCOUNT_AUD, BACKTEST_COST_SPI_AUD, BACKTEST_COST_AUDUSD_AUD constants"
      contains: "BACKTEST_INITIAL_ACCOUNT_AUD"
    - path: "backtest/__main__.py"
      provides: "python -m backtest dispatch"
    - path: "backtest/data_fetcher.py"
      provides: "I/O adapter skeleton (the ONE I/O exception per D-09)"
    - path: "backtest/simulator.py"
      provides: "pure-math simulator skeleton"
    - path: "backtest/metrics.py"
      provides: "pure-math metrics skeleton"
    - path: "backtest/render.py"
      provides: "pure HTML render skeleton"
    - path: "backtest/cli.py"
      provides: "argparse adapter skeleton"
    - path: "web/routes/backtest.py"
      provides: "FastAPI route adapter skeleton"
    - path: "tests/fixtures/backtest/golden_report.json"
      provides: "hand-authored reference report covering all D-05 fields"
      contains: "metadata"
    - path: "tests/test_signal_engine.py"
      provides: "BACKTEST_PATHS_PURE AST list + new test method"
      contains: "BACKTEST_PATHS_PURE"
  key_links:
    - from: "tests/test_signal_engine.py"
      to: "backtest/simulator.py + metrics.py + render.py"
      via: "AST walk against FORBIDDEN_MODULES (state_manager, notifier, dashboard, main, requests, datetime, os, yfinance)"
      pattern: "BACKTEST_PATHS_PURE"
    - from: "requirements.txt"
      to: ".venv/lib/python3.11/site-packages/pyarrow"
      via: "pip install -r requirements.txt"
      pattern: "pyarrow==24.0.0"
---

<objective>
Wave 0 — install pyarrow, create the backtest/ package skeleton, hand-author the golden report fixture, extend the AST hex-boundary guard, and create empty test files. This is the BLOCKING wave: every Wave 1 plan depends on these scaffolds existing. Tests created here are intentionally light (skeleton with fixture stubs); Wave 1+ plans fill them in.

Purpose: Provide failing-test scaffold + import-graph + binary dep so Wave 1 plans run in parallel without merge conflicts.
Output: 19 new/modified files; AST guard catches forbidden imports in pure backtest modules at PR time.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md
@.planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md
@.planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md
@CLAUDE.md
@requirements.txt
@tests/test_signal_engine.py
@system_params.py
@pnl_engine.py

<interfaces>
<!-- Existing AST guard structure (tests/test_signal_engine.py:488-600) -->
- FORBIDDEN_MODULES (line 492): frozenset of modules forbidden in pure-math hex
- FORBIDDEN_MODULES_STDLIB_ONLY = FORBIDDEN_MODULES | {'numpy', 'pandas'} (line 504)
- _HEX_PATHS_ALL (line 596): paths walked by test_forbidden_imports_absent
- _HEX_PATHS_STDLIB_ONLY (line 599): subset that also forbids numpy/pandas
- test_forbidden_imports_absent (line 770): @pytest.mark.parametrize('module_path', _HEX_PATHS_ALL)
- AST helper: parses module imports via ast.parse + ast.walk

<!-- system_params.py constants pattern (lines 25-27, 73-78) -->
SPI_MULT: float = 5.0   # AUD per point per contract (mini SPI 200)
AUDUSD_MULT: float = 10_000.0  # AUD per AUD/USD point per contract
SPI_COST_AUD: float = 6.0    # round-trip cost SPI200
AUDUSD_COST_AUD: float = 5.0 # round-trip cost AUDUSD
STRATEGY_VERSION: str = 'v1.2.0'

<!-- D-05 JSON schema (CONTEXT.md lines 93-143) — this is what golden_report.json must satisfy -->
{
  "metadata": {strategy_version, run_dt, years, end_date, start_date, initial_account_aud, cost_spi_aud, cost_audusd_aud, instruments},
  "metrics": {
    "combined": {cumulative_return_pct, sharpe_daily, max_drawdown_pct, win_rate, expectancy_aud, total_trades, pass},
    "SPI200": {<same fields>},
    "AUDUSD": {<same fields>}
  },
  "equity_curve": [{date, balance_spi, balance_audusd, balance_combined}, ...],
  "trades": [{open_dt, close_dt, instrument, side, entry_price, exit_price, contracts, entry_atr, exit_reason, gross_pnl_aud, cost_aud, net_pnl_aud, balance_after_aud, level}, ...]
}
</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| pip → .venv | Supply-chain: pinned exact pyarrow wheel from PyPI only |
| operator → .planning/backtests/data/*.parquet | Operator-controlled cache; recovery path = `--refresh` |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-23-pyarrow | Tampering/Supply-chain | requirements.txt | mitigate | Pin exact `pyarrow==24.0.0` (no `>=`, no `~=`); install via PyPI binary wheel only; verify with `pip show pyarrow` |
| T-23-cache-tamper | Tampering | .planning/backtests/data/*.parquet | mitigate | Parquet binary columnar (schema-typed, no eval/code paths on read); `--refresh` is recovery; .gitignore prevents accidental commit |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Pin pyarrow + .gitignore cache dir</name>
  <read_first>
    - requirements.txt — see existing pinned line shape (`pandas==2.3.3`, `numpy==2.0.2`, etc.)
    - .gitignore — see how `.planning/` paths are listed
    - .planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md §Standard Stack — confirms pyarrow 24.0.0 is latest, Python 3.11 wheel exists
  </read_first>
  <action>
    Append to `requirements.txt` (preserve existing alphabetical-ish order; add a new section header):

    ```
    # Phase 23 — backtest module dep (parquet engine for cache I/O)
    pyarrow==24.0.0
    ```

    Append to `.gitignore` (or create a Phase 23 block at the end):

    ```
    # Phase 23 — backtest parquet cache (per-machine, not committed)
    .planning/backtests/data/
    ```

    Then run `pip install -r requirements.txt` in .venv to install pyarrow.
  </action>
  <verify>
    <automated>pip show pyarrow | grep -E '^Version: 24\.0\.0'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c '^pyarrow==24.0.0$' requirements.txt` returns 1
    - `grep -c '^\.planning/backtests/data/$' .gitignore` returns 1
    - `pip show pyarrow | grep -c '^Version: 24\.0\.0'` returns 1
    - `python -c "import pyarrow; print(pyarrow.__version__)"` prints `24.0.0`
  </acceptance_criteria>
  <done>pyarrow 24.0.0 importable in .venv; cache dir git-ignored.</done>
</task>

<task type="auto">
  <name>Task 2: Create backtest/ package skeleton (7 files)</name>
  <read_first>
    - system_params.py lines 25-27, 73-78 — constants module convention (typed UPPER_SNAKE, comment trailers)
    - pnl_engine.py lines 1-55 — pure-math hex docstring + forbidden-imports declaration block
    - data_fetcher.py lines 1-25 — I/O hex docstring (the analog for backtest/data_fetcher.py)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md — analog mapping per file
    - .planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md §D-08 module structure
  </read_first>
  <action>
    Create the 7 files below as SKELETONS — each module loads + imports cleanly but functions raise `NotImplementedError` (Wave 1+ plans fill them in).

    **`backtest/__init__.py`:**
    ```python
    """Phase 23 — backtest module constants.

    Architecture: pure constants module (mirrors system_params.py role for backtest-scoped params).
    Forbidden imports: stdlib + typing only (this is a hex-pure constants module).
    Reuse `system_params.SPI_MULT` etc. via direct import in simulator.py — do NOT re-export here.
    """

    BACKTEST_INITIAL_ACCOUNT_AUD: float = 10_000.0  # AUD per CONTEXT D-02 (locked)
    BACKTEST_COST_SPI_AUD: float = 6.0              # AUD round-trip per CLAUDE.md D-11
    BACKTEST_COST_AUDUSD_AUD: float = 5.0           # AUD round-trip per CLAUDE.md D-11
    BACKTEST_DEFAULT_YEARS: int = 5                 # CONTEXT D-03
    BACKTEST_PASS_THRESHOLD_PCT: float = 100.0      # CONTEXT D-16 (strict greater-than)
    BACKTEST_CACHE_TTL_SECONDS: int = 86_400        # 24h, CONTEXT D-01
    ```

    **`backtest/__main__.py`:**
    ```python
    """Phase 23 — enables `python -m backtest`. Dispatches to backtest.cli.main()."""
    from backtest.cli import main

    if __name__ == '__main__':
      raise SystemExit(main())
    ```

    **`backtest/data_fetcher.py`:**
    ```python
    """Phase 23 — I/O adapter for backtest module (the ONE I/O exception per CONTEXT D-09).

    Wraps yfinance with parquet cache at `.planning/backtests/data/<symbol>-<from>-<to>.parquet`.
    24h staleness; --refresh forces re-fetch.

    EXPLICITLY EXCLUDED from BACKTEST_PATHS_PURE AST guard (tests/test_signal_engine.py).
    This is the documented I/O exception per CONTEXT D-09; do NOT add to any pure-AST list.

    Allowed imports per D-09: yfinance, pyarrow, pandas, pathlib, datetime, dateutil, logging, time.
    Forbidden: state_manager, notifier, dashboard, main, sibling backtest/ pure modules.
    """
    from __future__ import annotations
    # Wave 1 Plan 23-02 fills in fetch_ohlcv() and cache helpers.

    def fetch_ohlcv(symbol: str, start: str, end: str, refresh: bool = False):
      raise NotImplementedError('Phase 23 Wave 1 Plan 02 — to be implemented')
    ```

    **`backtest/simulator.py`:**
    ```python
    """Phase 23 — bar-by-bar replay simulator.

    Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY.
    Reuses signal_engine.compute_indicators + sizing_engine.step verbatim per CONTEXT D-10.

    Forbidden imports (enforced by tests/test_signal_engine.py BACKTEST_PATHS_PURE AST guard):
      state_manager, notifier, dashboard, main, requests, datetime, os, yfinance, schedule.
    Allowed: math, typing, system_params, signal_engine, sizing_engine, pandas, numpy.
    """
    from __future__ import annotations

    def simulate(df, instrument: str, multiplier: float, cost_round_trip_aud: float,
                 initial_account_aud: float):
      raise NotImplementedError('Phase 23 Wave 1 Plan 03 — to be implemented')
    ```

    **`backtest/metrics.py`:**
    ```python
    """Phase 23 — pure aggregation: Sharpe / max DD / win rate / expectancy / cum return.

    Architecture (hexagonal-lite, CLAUDE.md): pure math ONLY.
    Forbidden imports (BACKTEST_PATHS_PURE AST guard): same as simulator.py.
    Allowed: math, statistics, typing, pandas, numpy.

    Pass criterion (CONTEXT D-16): cumulative_return_pct > 100.0 STRICT.
    """
    from __future__ import annotations

    def compute_metrics(equity_curve: list[float], trades: list[dict]) -> dict:
      raise NotImplementedError('Phase 23 Wave 1 Plan 04 — to be implemented')
    ```

    **`backtest/render.py`:**
    ```python
    """Phase 23 — pure HTML render for /backtest report + history + override form.

    Architecture (hexagonal-lite, CLAUDE.md): pure render. NO I/O, NO env vars, NO clock injection.
    DOES NOT IMPORT dashboard.py per CONTEXT D-07 — Chart.js URL+SRI duplicated below.

    Forbidden imports (BACKTEST_PATHS_PURE AST guard): same as simulator.py.
    Allowed: html (escape), json, typing.
    """
    from __future__ import annotations
    import html
    import json

    # Chart.js 4.4.6 UMD CDN constants — DUPLICATED from dashboard.py:113-116 per D-07.
    _CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.js'
    _CHARTJS_SRI = 'sha384-MH1axGwz/uQzfIcjFdjEfsM0xlf5mmWfAwwggaOh5IPFvgKFGbJ2PZ4VBbgSYBQN'

    def render_report(report: dict) -> str:
      raise NotImplementedError('Phase 23 Wave 2 Plan 05 — to be implemented')

    def render_history(reports: list[dict]) -> str:
      raise NotImplementedError('Phase 23 Wave 2 Plan 05 — to be implemented')

    def render_run_form(defaults: dict) -> str:
      raise NotImplementedError('Phase 23 Wave 2 Plan 05 — to be implemented')
    ```

    **`backtest/cli.py`:**
    ```python
    """Phase 23 — argparse CLI for `python -m backtest`.

    Surface (CONTEXT D-11):
      --years (default 5), --end-date YYYY-MM-DD, --initial-account 10000,
      --cost-spi 6.0, --cost-audusd 5.0, --refresh, --output PATH

    Log prefix: [Backtest] — NEW per CLAUDE.md log-prefix convention + CONTEXT D-11.
    Exit codes: 0 = PASS (cumulative_return_pct > 100), 1 = FAIL.
    """
    from __future__ import annotations

    def main(argv: list[str] | None = None) -> int:
      raise NotImplementedError('Phase 23 Wave 2 Plan 06 — to be implemented')
    ```

    Run `python -c "import backtest; from backtest import cli, simulator, metrics, render, data_fetcher; print('ok')"` to verify import graph.
  </action>
  <verify>
    <automated>python -c "import backtest; from backtest import cli, simulator, metrics, render, data_fetcher; from backtest.cli import main; from backtest.simulator import simulate; from backtest.metrics import compute_metrics; from backtest.render import render_report, render_history, render_run_form; from backtest.data_fetcher import fetch_ohlcv; print('ok')" 2>&1 | grep -c '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - 7 files exist under `backtest/` (`__init__.py`, `__main__.py`, `data_fetcher.py`, `simulator.py`, `metrics.py`, `render.py`, `cli.py`)
    - `python -c "import backtest"` succeeds with no error
    - `python -c "from backtest import BACKTEST_INITIAL_ACCOUNT_AUD; assert BACKTEST_INITIAL_ACCOUNT_AUD == 10_000.0"` succeeds
    - `grep -c "^_CHARTJS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.6" backtest/render.py` returns 1
    - `grep -c "^_CHARTJS_SRI = 'sha384-MH1axGwz" backtest/render.py` returns 1
    - `grep -c '^import dashboard\|^from dashboard' backtest/render.py` returns 0 (D-07)
  </acceptance_criteria>
  <done>backtest/ package importable; all 7 modules expose their public surface as NotImplementedError stubs.</done>
</task>

<task type="auto">
  <name>Task 3: Create web/routes/backtest.py skeleton + mount in web/app.py</name>
  <read_first>
    - web/routes/paper_trades.py lines 1-50 — module docstring + register() factory pattern
    - web/routes/paper_trades.py lines 228-302 — POST handler with Form(...) + 303 RedirectResponse
    - web/app.py lines 40-48 (imports) and 156-160 (registration)
    - .planning/phases/23-five-year-backtest-validation-gate/23-RESEARCH.md §Pattern 5 + §Pattern 8
  </read_first>
  <action>
    Create `web/routes/backtest.py` as a SKELETON with the 4 routes per CONTEXT D-12 (handler bodies raise `NotImplementedError`; structure complete enough for AST/import checks):

    ```python
    """Phase 23 — web routes for /backtest report + history + override form.

    Routes (CONTEXT D-12):
      GET  /backtest              — latest report from .planning/backtests/*.json (sorted by mtime desc)
      GET  /backtest?history=true — D-06 table + 10-run overlay chart
      GET  /backtest?run=<file>   — specified report (path-traversal guarded per RESEARCH §Pattern 5)
      POST /backtest/run          — operator override form (D-14)

    Auth: Phase 16.1 cookie-session middleware gates all paths uniformly. No per-route auth code.
    Hex tier: adapter — imports backtest/*, FastAPI, system_params, web.middleware (transitively).
            Does NOT import signal_engine, sizing_engine directly (those go through backtest.simulator).
    """
    from __future__ import annotations
    import os
    import re
    from pathlib import Path

    from fastapi import FastAPI, Form, Request
    from fastapi.responses import HTMLResponse, RedirectResponse

    _LOG_PREFIX = '[Web]'  # web layer keeps [Web]; CLI uses [Backtest]
    _BACKTEST_DIR = Path('.planning/backtests')
    _SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9._-]+\.json$')


    def _resolve_safe_backtest_path(filename: str) -> Path:
      """Two-layer defence: regex gate + os.listdir whitelist (RESEARCH §Pattern 5).

      Raises ValueError on any path-traversal attempt or unknown filename.
      """
      raise NotImplementedError('Phase 23 Wave 2 Plan 06 — to be implemented')


    async def get_backtest(request: Request) -> HTMLResponse:
      raise NotImplementedError('Phase 23 Wave 2 Plan 06 — to be implemented')


    async def post_backtest_run(
      request: Request,
      initial_account_aud: float = Form(...),
      cost_spi_aud: float = Form(...),
      cost_audusd_aud: float = Form(...),
    ) -> RedirectResponse:
      raise NotImplementedError('Phase 23 Wave 2 Plan 06 — to be implemented')


    def register(app: FastAPI) -> None:
      """Mount Phase 23 routes; called from web/app.py:create_app()."""
      app.add_api_route('/backtest', get_backtest, methods=['GET'])
      app.add_api_route('/backtest/run', post_backtest_run, methods=['POST'])
    ```

    Then mount in `web/app.py`:
    1. Add to imports block adjacent to `paper_trades_route` import (around line 47):
       ```python
       from web.routes import backtest as backtest_route
       ```
    2. Add to `create_app()` adjacent to `paper_trades_route.register(application)` (line 160):
       ```python
       backtest_route.register(application)  # Phase 23 D-12: backtest validation gate
       ```
  </action>
  <verify>
    <automated>python -c "from web.routes import backtest as b; from web.app import create_app; app = create_app(); paths = sorted({r.path for r in app.routes}); assert '/backtest' in paths and '/backtest/run' in paths, paths; print('ok')" 2>&1 | grep -c '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `web/routes/backtest.py` exists and imports cleanly
    - `grep -c "from web.routes import backtest as backtest_route" web/app.py` returns 1
    - `grep -c "backtest_route.register(application)" web/app.py` returns 1
    - `grep -c "^import signal_engine\|^from signal_engine\|^import sizing_engine\|^from sizing_engine" web/routes/backtest.py` returns 0 (web layer must not import engines directly)
    - Route registration check: `python -c "from web.app import create_app; app=create_app(); print(sorted({r.path for r in app.routes}))"` includes `/backtest` and `/backtest/run`
  </acceptance_criteria>
  <done>web/routes/backtest.py skeleton mounted; FastAPI sees /backtest GET and /backtest/run POST routes.</done>
</task>

<task type="auto">
  <name>Task 4: Extend AST guard in tests/test_signal_engine.py for BACKTEST_PATHS_PURE</name>
  <read_first>
    - tests/test_signal_engine.py lines 480-600 — full FORBIDDEN_MODULES + _HEX_PATHS_* declarations
    - tests/test_signal_engine.py lines 769-810 — test_forbidden_imports_absent + the existing AST helper
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"tests/test_signal_engine.py extension"
    - .planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md §D-09
  </read_first>
  <action>
    Edit `tests/test_signal_engine.py`:

    1. Around line 595-600 (after the existing `_HEX_PATHS_ALL` and `_HEX_PATHS_STDLIB_ONLY` declarations), ADD the Phase 23 paths:

    ```python
    # Phase 23: backtest pure-math hex tier (BACKTEST-01..04 + D-09).
    # simulator.py / metrics.py / render.py — pure ONLY but ALLOWED to import
    # signal_engine, sizing_engine, pandas, numpy (different from STDLIB_ONLY).
    # data_fetcher.py is the documented I/O exception (CONTEXT D-09) — NOT added here.
    BACKTEST_SIMULATOR_PATH = Path('backtest/simulator.py')
    BACKTEST_METRICS_PATH = Path('backtest/metrics.py')
    BACKTEST_RENDER_PATH = Path('backtest/render.py')
    _BACKTEST_PATHS_PURE = [BACKTEST_SIMULATOR_PATH, BACKTEST_METRICS_PATH, BACKTEST_RENDER_PATH]

    # Backtest pure modules forbid all of FORBIDDEN_MODULES PLUS pyarrow.
    # render.py legitimately needs json+html (Chart.js payload, html.escape) — handled per-file below.
    FORBIDDEN_MODULES_BACKTEST_PURE = FORBIDDEN_MODULES | frozenset({'pyarrow'})
    ```

    Also ADD `BACKTEST_SIMULATOR_PATH`, `BACKTEST_METRICS_PATH`, `BACKTEST_RENDER_PATH` to the existing `_HEX_PATHS_ALL` list (line 596) so the broad `test_forbidden_imports_absent` walks them too:

    ```python
    _HEX_PATHS_ALL = [SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH, PNL_ENGINE_PATH,
                     ALERT_ENGINE_PATH,
                     # Phase 23 backtest pure-math hex
                     BACKTEST_SIMULATOR_PATH, BACKTEST_METRICS_PATH, BACKTEST_RENDER_PATH]
    ```

    BUT: existing `FORBIDDEN_MODULES` includes `json` (line 494) which `render.py` LEGITIMATELY uses for Chart.js payload injection (RESEARCH §Pattern 4). Solution: render.py is EXCLUDED from `_HEX_PATHS_ALL` and instead handled by the new dedicated test method below.

    Revised: only add `BACKTEST_SIMULATOR_PATH` and `BACKTEST_METRICS_PATH` to `_HEX_PATHS_ALL`. Do NOT add `BACKTEST_RENDER_PATH` to `_HEX_PATHS_ALL` — it goes through the dedicated method which has the `json`+`html` allowance.

    ```python
    _HEX_PATHS_ALL = [SIGNAL_ENGINE_PATH, SIZING_ENGINE_PATH, SYSTEM_PARAMS_PATH, PNL_ENGINE_PATH,
                     ALERT_ENGINE_PATH,
                     # Phase 23 — simulator and metrics only (render.py uses json+html legitimately
                     # and is checked by test_backtest_render_no_forbidden_imports below)
                     BACKTEST_SIMULATOR_PATH, BACKTEST_METRICS_PATH]
    ```

    2. Around line 769 (after the existing `test_forbidden_imports_absent` method), ADD a NEW test method inside `TestDeterminism`:

    ```python
      def test_backtest_render_no_forbidden_imports(self) -> None:
        """Phase 23 D-09: backtest/render.py has the same forbidden-imports rule
        as simulator/metrics PLUS pyarrow, but is ALLOWED `json` and `html` from stdlib
        (Chart.js JSON payload defence + html.escape — RESEARCH §Pattern 4).

        backtest/data_fetcher.py is the documented I/O exception (CONTEXT D-09) and
        is NOT checked here.
        """
        path = BACKTEST_RENDER_PATH
        if not path.exists():
          pytest.skip(f'{path} not yet created (Wave 0 dep)')

        # Reuse the existing AST import-collection helper (replicate the inline
        # `ast.parse + ast.walk` pattern used by test_forbidden_imports_absent).
        source = path.read_text()
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
          if isinstance(node, ast.Import):
            for alias in node.names:
              imports.add(alias.name.split('.')[0])
          elif isinstance(node, ast.ImportFrom):
            if node.module:
              imports.add(node.module.split('.')[0])

        # render.py forbids the FULL FORBIDDEN_MODULES set EXCEPT json (Chart.js
        # payload) and html (html.escape) — both stdlib, no I/O. Also forbid pyarrow.
        forbidden_for_render = (FORBIDDEN_MODULES | frozenset({'pyarrow'})) - frozenset({'json'})
        leaked = imports & forbidden_for_render
        assert not leaked, (
          f'{path} imports forbidden modules: {sorted(leaked)} '
          f'(BACKTEST render hex-boundary D-09 violation; html+json legitimate, others not)'
        )
    ```

    Also add `import ast` at the top of the test file if not already present (check imports section, around line 1-30; existing AST tests likely already import it).

    3. Verify `test_forbidden_imports_absent` (existing, line 770) now also runs against `BACKTEST_SIMULATOR_PATH` and `BACKTEST_METRICS_PATH` because they're in `_HEX_PATHS_ALL`. The skeletons created in Task 2 only import `from __future__ import annotations` — no forbidden modules — so the test will pass.

    NOTE: For simulator and metrics, `pyarrow` is NOT in FORBIDDEN_MODULES yet. To enforce the pyarrow ban for these modules too, ADD a second new test method:

    ```python
      @pytest.mark.parametrize('module_path', [BACKTEST_SIMULATOR_PATH, BACKTEST_METRICS_PATH, BACKTEST_RENDER_PATH])
      def test_backtest_pure_no_pyarrow_import(self, module_path: Path) -> None:
        """Phase 23 D-09: backtest pure modules (simulator/metrics/render) must NOT import
        pyarrow — that lives in data_fetcher.py only (the I/O exception)."""
        if not module_path.exists():
          pytest.skip(f'{module_path} not yet created (Wave 0 dep)')

        source = module_path.read_text()
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
          if isinstance(node, ast.Import):
            for alias in node.names:
              imports.add(alias.name.split('.')[0])
          elif isinstance(node, ast.ImportFrom):
            if node.module:
              imports.add(node.module.split('.')[0])
        assert 'pyarrow' not in imports, (
          f'{module_path} imports pyarrow — backtest pure modules forbid pyarrow per D-09; '
          f'pyarrow lives only in backtest/data_fetcher.py (the documented I/O exception)'
        )
    ```
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism -x -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c '^BACKTEST_SIMULATOR_PATH = Path' tests/test_signal_engine.py` returns 1
    - `grep -c '^BACKTEST_METRICS_PATH = Path' tests/test_signal_engine.py` returns 1
    - `grep -c '^BACKTEST_RENDER_PATH = Path' tests/test_signal_engine.py` returns 1
    - `grep -c '_BACKTEST_PATHS_PURE' tests/test_signal_engine.py` returns ≥1
    - `grep -c 'def test_backtest_render_no_forbidden_imports' tests/test_signal_engine.py` returns 1
    - `grep -c 'def test_backtest_pure_no_pyarrow_import' tests/test_signal_engine.py` returns 1
    - `grep -c 'BACKTEST_SIMULATOR_PATH' tests/test_signal_engine.py | head -1` confirms it appears in `_HEX_PATHS_ALL` declaration too
    - `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_backtest_render_no_forbidden_imports -x -q` passes
    - `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_backtest_pure_no_pyarrow_import -x -q` passes (3 parametrized)
    - `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism::test_forbidden_imports_absent -x -q` continues to pass (regression check; now 7 parametrized cases)
  </acceptance_criteria>
  <done>AST guard catches forbidden imports + pyarrow leakage in backtest/simulator.py, metrics.py, render.py at PR time.</done>
</task>

<task type="auto">
  <name>Task 5: Hand-author tests/fixtures/backtest/golden_report.json</name>
  <read_first>
    - .planning/phases/23-five-year-backtest-validation-gate/23-CONTEXT.md §D-05 (full JSON schema)
    - .planning/phases/23-five-year-backtest-validation-gate/23-PATTERNS.md §"tests/fixtures/backtest/golden_report.json"
    - tests/fixtures/state_v6_with_paper_trades.json — fixture style precedent
    - .planning/phases/23-five-year-backtest-validation-gate/23-VALIDATION.md
  </read_first>
  <action>
    Create directory `tests/fixtures/backtest/` and hand-author `golden_report.json` covering ALL D-05 fields:

    - 1 trade per instrument (2 trades total, both closed, deterministic prices)
    - 4 equity_curve points (covers a non-monotonic path so max-DD test has signal)
    - All 6 metrics fields per instrument + combined
    - Both `sharpe_daily` (raw mean/std) AND `sharpe_annualized` (× √252) per planner D-19 (PATTERNS.md "Dual-Sharpe formula")
    - `metadata.pass = true` for combined (cumulative_return_pct = 127.45 > 100.0)
    - `metadata.strategy_version = "v1.2.0"` matching system_params
    - Realistic prices: SPI200 ~7800, AUDUSD ~0.65

    File contents (~3-5 KB):

    ```json
    {
      "metadata": {
        "strategy_version": "v1.2.0",
        "run_dt": "2026-05-01T08:00:00+08:00",
        "years": 5,
        "end_date": "2026-05-01",
        "start_date": "2021-05-01",
        "initial_account_aud": 10000.0,
        "cost_spi_aud": 6.0,
        "cost_audusd_aud": 5.0,
        "instruments": ["SPI200", "AUDUSD"],
        "pass": true
      },
      "metrics": {
        "combined": {
          "cumulative_return_pct": 127.45,
          "sharpe_daily": 0.053,
          "sharpe_annualized": 0.84,
          "max_drawdown_pct": -23.10,
          "win_rate": 0.5,
          "expectancy_aud": 188.25,
          "total_trades": 2,
          "pass": true
        },
        "SPI200": {
          "cumulative_return_pct": 110.20,
          "sharpe_daily": 0.048,
          "sharpe_annualized": 0.76,
          "max_drawdown_pct": -18.50,
          "win_rate": 1.0,
          "expectancy_aud": 376.50,
          "total_trades": 1,
          "pass": true
        },
        "AUDUSD": {
          "cumulative_return_pct": 95.10,
          "sharpe_daily": 0.041,
          "sharpe_annualized": 0.65,
          "max_drawdown_pct": -23.10,
          "win_rate": 0.0,
          "expectancy_aud": 0.0,
          "total_trades": 1,
          "pass": false
        }
      },
      "equity_curve": [
        {"date": "2021-05-01", "balance_spi": 10000.0, "balance_audusd": 10000.0, "balance_combined": 20000.0},
        {"date": "2021-05-12", "balance_spi": 10376.50, "balance_audusd": 10000.0, "balance_combined": 20376.50},
        {"date": "2025-12-15", "balance_spi": 10376.50, "balance_audusd": 9510.00, "balance_combined": 19886.50},
        {"date": "2026-05-01", "balance_spi": 11020.0, "balance_audusd": 9510.00, "balance_combined": 20530.0}
      ],
      "trades": [
        {
          "open_dt": "2021-05-04",
          "close_dt": "2021-05-12",
          "instrument": "SPI200",
          "side": "LONG",
          "entry_price": 7012.5,
          "exit_price": 7089.0,
          "contracts": 1,
          "entry_atr": 35.2,
          "exit_reason": "signal_reversal",
          "gross_pnl_aud": 382.50,
          "cost_aud": 6.0,
          "net_pnl_aud": 376.50,
          "balance_after_aud": 10376.50,
          "level": 1
        },
        {
          "open_dt": "2025-09-01",
          "close_dt": "2025-12-15",
          "instrument": "AUDUSD",
          "side": "SHORT",
          "entry_price": 0.6520,
          "exit_price": 0.6569,
          "contracts": 1,
          "entry_atr": 0.0085,
          "exit_reason": "trailing_stop",
          "gross_pnl_aud": -485.00,
          "cost_aud": 5.0,
          "net_pnl_aud": -490.00,
          "balance_after_aud": 9510.00,
          "level": 1
        }
      ]
    }
    ```

    IMPORTANT: Use `exit_reason` values from the planner D-20 mapping in PATTERNS.md (`flat_signal`, `signal_reversal`, `trailing_stop`, `adx_drop`, `manual_stop`) — NOT D-05's `signal_change`. The fixture uses `signal_reversal` and `trailing_stop` to exercise both common branches.
  </action>
  <verify>
    <automated>python -c "import json, pathlib; r=json.loads(pathlib.Path('tests/fixtures/backtest/golden_report.json').read_text()); assert set(r) == {'metadata','metrics','equity_curve','trades'}; assert set(r['metrics']) == {'combined','SPI200','AUDUSD'}; assert r['metrics']['combined']['pass'] is True; assert r['metrics']['combined']['cumulative_return_pct'] > 100.0; assert len(r['trades']) == 2; assert all(t['exit_reason'] in {'flat_signal','signal_reversal','trailing_stop','adx_drop','manual_stop'} for t in r['trades']); print('ok')" 2>&1 | grep -c '^ok$'</automated>
  </verify>
  <acceptance_criteria>
    - `tests/fixtures/backtest/golden_report.json` exists
    - Validates as JSON with no errors
    - Has top-level keys: metadata, metrics, equity_curve, trades
    - metrics has combined + SPI200 + AUDUSD sub-objects
    - combined.cumulative_return_pct > 100.0 and combined.pass == true
    - All trades use exit_reason values from {flat_signal, signal_reversal, trailing_stop, adx_drop, manual_stop} (planner D-20)
    - Both sharpe_daily AND sharpe_annualized fields present per metric block (planner D-19)
    - File size between 1500-6000 bytes
  </acceptance_criteria>
  <done>Golden fixture exists with full D-05 schema; downstream render tests can load it without running the simulator.</done>
</task>

<task type="auto">
  <name>Task 6: Create 6 empty test file skeletons</name>
  <read_first>
    - tests/test_pnl_engine.py lines 1-50 — pure-math test file structure
    - tests/test_web_paper_trades.py lines 1-50 — web route test file structure
    - tests/conftest.py lines 92-101 (valid_cookie_token fixture) and 312-362 (client_with_state_v6)
    - .planning/phases/23-five-year-backtest-validation-gate/23-VALIDATION.md (Per-Task Verification Map — these test files back the automated commands)
  </read_first>
  <action>
    Create 6 test files with skeletons. Each contains class definitions + at least one `pytest.skip("Wave 1+ to implement")` test inside each named test class so the verify automation map (VALIDATION.md) can resolve `pytest tests/test_backtest_*.py::TestXxx -x` to a runnable identifier.

    **`tests/test_backtest_data_fetcher.py`:**
    ```python
    """Phase 23 — backtest/data_fetcher.py tests (BACKTEST-01 data layer).

    Coverage: cache hit/miss, --refresh, parquet round-trip, <5y bail.
    Wave 1 Plan 23-02 fills these in.
    """
    from __future__ import annotations
    import pytest


    class TestCacheHitMiss:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 02 — to be implemented')


    class TestParquetRoundTrip:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 02 — to be implemented')


    class TestRefreshFlag:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 02 — to be implemented')


    class TestShortDataBail:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 02 — to be implemented')
    ```

    **`tests/test_backtest_simulator.py`:**
    ```python
    """Phase 23 — backtest/simulator.py tests (BACKTEST-01 replay).

    Coverage: determinism, sizing reuse, exit reasons, cost reconstruction, NaN-safe.
    Wave 1 Plan 23-03 fills these in.
    """
    from __future__ import annotations
    import pytest


    class TestDeterminism:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 03 — to be implemented')


    class TestCostModel:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 03 — to be implemented')


    class TestExitReasons:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 03 — to be implemented')


    class TestNanSafety:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 03 — to be implemented')
    ```

    **`tests/test_backtest_metrics.py`:**
    ```python
    """Phase 23 — backtest/metrics.py tests (BACKTEST-02 formulas)."""
    from __future__ import annotations
    import pytest


    class TestCumulativeReturn:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 04 — to be implemented')


    class TestSharpe:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 04 — to be implemented')


    class TestMaxDrawdown:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 04 — to be implemented')


    class TestWinRateExpectancy:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 04 — to be implemented')


    class TestPassCriterion:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 1 Plan 04 — to be implemented')
    ```

    **`tests/test_backtest_render.py`:**
    ```python
    """Phase 23 — backtest/render.py tests (BACKTEST-03 HTML)."""
    from __future__ import annotations
    import pytest


    class TestRenderReport:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 05 — to be implemented')


    class TestChartJsSri:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 05 — to be implemented')


    class TestRenderHistory:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 05 — to be implemented')


    class TestRenderRunForm:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 05 — to be implemented')


    class TestEmptyState:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 05 — to be implemented')


    class TestJsonInjectionDefence:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 05 — to be implemented')
    ```

    **`tests/test_backtest_cli.py`:**
    ```python
    """Phase 23 — backtest/cli.py tests (BACKTEST-04 CLI)."""
    from __future__ import annotations
    import pytest


    class TestArgparse:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 06 — to be implemented')


    class TestJsonSchema:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 06 — to be implemented')


    class TestExitCode:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 06 — to be implemented')


    class TestLogFormat:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 06 — to be implemented')


    class TestStrategyVersionTagging:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 06 — to be implemented')
    ```

    **`tests/test_web_backtest.py`:**
    ```python
    """Phase 23 — web/routes/backtest.py tests (BACKTEST-03/04 web routes)."""
    from __future__ import annotations
    import pytest


    class TestGetBacktest:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 07 — to be implemented')


    class TestPathTraversal:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 07 — to be implemented')


    class TestPostRun:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 07 — to be implemented')


    class TestCookieAuth:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 07 — to be implemented')


    class TestHistoryView:
      def test_skeleton(self):
        pytest.skip('Phase 23 Wave 2 Plan 07 — to be implemented')
    ```
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_backtest_data_fetcher.py tests/test_backtest_simulator.py tests/test_backtest_metrics.py tests/test_backtest_render.py tests/test_backtest_cli.py tests/test_web_backtest.py --collect-only -q 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - All 6 test files exist
    - `pytest --collect-only` collects all classes (TestCacheHitMiss, TestCostModel, TestSharpe, TestChartJsSri, TestExitCode, TestPathTraversal, etc.)
    - All tests are SKIPPED (not failing) when run: `pytest tests/test_backtest_*.py tests/test_web_backtest.py -x` exits 0 with all-skip
    - `grep -c "class TestPathTraversal" tests/test_web_backtest.py` returns 1 (referenced by VALIDATION.md)
    - `grep -c "class TestChartJsSri" tests/test_backtest_render.py` returns 1
    - `grep -c "class TestCostModel" tests/test_backtest_simulator.py` returns 1
    - `grep -c "class TestJsonSchema" tests/test_backtest_cli.py` returns 1
    - `grep -c "class TestExitCode" tests/test_backtest_cli.py` returns 1
    - `grep -c "class TestPostRun" tests/test_web_backtest.py` returns 1
    - `grep -c "class TestGetBacktest" tests/test_web_backtest.py` returns 1
  </acceptance_criteria>
  <done>All test classes referenced in VALIDATION.md exist as skeletons; full pytest run is green (skips don't fail).</done>
</task>

</tasks>

<verification>
After all 6 tasks:
1. `pip show pyarrow | grep -E '^Version: 24\.0\.0$'` returns one match
2. `python -c "import backtest; from backtest import cli, simulator, metrics, render, data_fetcher; print('ok')"` prints `ok`
3. `python -c "from web.app import create_app; app=create_app(); paths=sorted({r.path for r in app.routes}); assert '/backtest' in paths and '/backtest/run' in paths"` succeeds
4. `.venv/bin/pytest tests/test_signal_engine.py::TestDeterminism -x -q` passes (existing tests + new test_backtest_render_no_forbidden_imports + test_backtest_pure_no_pyarrow_import)
5. `.venv/bin/pytest tests/test_backtest_*.py tests/test_web_backtest.py -q` exits 0 (all skipped)
6. `python -c "import json, pathlib; r=json.loads(pathlib.Path('tests/fixtures/backtest/golden_report.json').read_text()); assert r['metrics']['combined']['pass']"` succeeds
7. `grep -c '^\.planning/backtests/data/$' .gitignore` returns 1
</verification>

<success_criteria>
- pyarrow 24.0.0 pinned and installed
- backtest/ package with 7 modules importable
- web/routes/backtest.py registered in web/app.py with /backtest GET + /backtest/run POST routes
- AST guard extends to backtest/{simulator,metrics,render}.py with proper allowlist
- Golden report fixture matches D-05 schema fully (incl. dual sharpe per planner D-19, exit_reason mapping per planner D-20)
- All 6 test files exist with named classes referenced in VALIDATION.md
- Full pytest suite: green or skip only (no new failures)
</success_criteria>

<output>
Create `.planning/phases/23-five-year-backtest-validation-gate/23-01-SUMMARY.md` after completion documenting:
- pyarrow install confirmation (`pip show pyarrow` output)
- backtest/ skeleton import graph proof
- AST guard extension diff summary
- Golden fixture schema validation result
- All 6 test files collection summary
- Any Rule-1 deviations encountered
</output>
