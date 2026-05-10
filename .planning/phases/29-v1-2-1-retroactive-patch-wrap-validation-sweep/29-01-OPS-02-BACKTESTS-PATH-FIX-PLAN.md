---
phase: 29
plan_id: 29-01-OPS-02-BACKTESTS-PATH-FIX
plan: 01
type: execute
wave: 1
depends_on: []
requirements: [OPS-02]
files_modified:
  - backtest/cli.py
  - backtest/data_fetcher.py
  - web/routes/backtest.py
  - tests/test_backtest_path_resolution.py
autonomous: true
must_haves:
  truths:
    - "`python -m backtest --years N` resolves output to `<project_root>/.planning/backtests/` regardless of caller CWD."
    - "`/backtest` route resolves report dir to `<project_root>/.planning/backtests/` regardless of uvicorn CWD."
    - "Subprocess regression test invoking `python -m backtest` from `/tmp` AND project root produces identical resolved output paths."
  artifacts:
    - path: "backtest/cli.py"
      provides: "Module-level `Path(__file__).resolve().parents[N]`-anchored `_BACKTEST_DIR` constant"
      contains: "Path(__file__).resolve().parents"
    - path: "backtest/data_fetcher.py"
      provides: "Module-level `Path(__file__).resolve().parents[N]`-anchored `_CACHE_DIR_DEFAULT` constant"
      contains: "Path(__file__).resolve().parents"
    - path: "web/routes/backtest.py"
      provides: "Module-level `Path(__file__).resolve().parents[N]`-anchored `_BACKTEST_DIR` constant"
      contains: "Path(__file__).resolve().parents"
    - path: "tests/test_backtest_path_resolution.py"
      provides: "Subprocess-level CWD-invariance test"
      contains: "subprocess.run"
  key_links:
    - from: "backtest/cli.py:46 (_BACKTEST_DIR)"
      to: "filesystem write at backtest/cli.py:121"
      via: "Path(__file__).resolve().parents[N] / '.planning/backtests'"
      pattern: "Path\\(__file__\\)\\.resolve\\(\\)\\.parents"
    - from: "backtest/data_fetcher.py:24 (_CACHE_DIR_DEFAULT)"
      to: "cache dir at backtest/data_fetcher.py:132"
      via: "Path(__file__).resolve().parents[N] / '.planning/backtests/data'"
      pattern: "Path\\(__file__\\)\\.resolve\\(\\)\\.parents"
    - from: "web/routes/backtest.py:45 (_BACKTEST_DIR)"
      to: "report listing at web/routes/backtest.py:59,76"
      via: "Path(__file__).resolve().parents[N] / '.planning/backtests'"
      pattern: "Path\\(__file__\\)\\.resolve\\(\\)\\.parents"
---

<objective>
Fix OPS-02: replace CWD-relative `.planning/backtests/` paths in 3 callers with module-level `Path(__file__).resolve().parents[N]` anchors so `python -m backtest` and `/backtest` resolve identically regardless of caller CWD. Honours D-14 (per-module locality) and D-15 (most-eloquent: no `paths.py` helper).

Purpose: Today `python -m backtest --years 5` from `/tmp` writes to `/tmp/.planning/backtests/...` and the `/backtest` route 404s reports written from the CLI when run elsewhere. Closes ROADMAP SC-4.
Output: 3 modules with module-level project-root anchors + 1 subprocess regression test (D-16).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-CONTEXT.md
@CLAUDE.md
@.claude/LEARNINGS.md

<read_first>
- `backtest/cli.py` (current `_BACKTEST_DIR = Path('.planning/backtests')` at line 46)
- `backtest/data_fetcher.py` (current `_CACHE_DIR_DEFAULT = Path('.planning/backtests/data')` at line 24)
- `web/routes/backtest.py` (current `_BACKTEST_DIR = Path('.planning/backtests')` at line 45)
- 29-CONTEXT.md §D-14, D-15, D-16 (locality + subprocess test contract)
</read_first>

<interfaces>
All three current call sites already use `_BACKTEST_DIR` / `_CACHE_DIR_DEFAULT` module-level constants. The fix is anchor swap only — no contract change at function boundaries.

Project root from each module:
- `backtest/cli.py` → `Path(__file__).resolve().parents[1]` (project root is `backtest/`'s parent)
- `backtest/data_fetcher.py` → `Path(__file__).resolve().parents[1]`
- `web/routes/backtest.py` → `Path(__file__).resolve().parents[2]` (project root is `web/routes/`'s grandparent)

Verify each `parents[N]` selection by confirming `(Path(__file__).resolve().parents[N] / 'backtest').is_dir()` resolves true at write time.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Anchor 3 backtest path constants to project root</name>
  <files>backtest/cli.py, backtest/data_fetcher.py, web/routes/backtest.py</files>
  <read_first>
    - backtest/cli.py:1-50 (imports + module-level constants region)
    - backtest/data_fetcher.py:1-30
    - web/routes/backtest.py:1-50
    - 29-CONTEXT.md §D-14, D-15
  </read_first>
  <action>
    Per D-14/D-15: replace each CWD-relative path constant with a module-local `Path(__file__).resolve().parents[N]`-anchored constant.

    1. `backtest/cli.py:46` — change:
       ```python
       _BACKTEST_DIR = Path('.planning/backtests')
       ```
       to:
       ```python
       _PROJECT_ROOT = Path(__file__).resolve().parents[1]
       _BACKTEST_DIR = _PROJECT_ROOT / '.planning' / 'backtests'
       ```
       Confirm `parents[1]` lands on project root by checking `(parents[1] / 'backtest').is_dir()` resolves true; adjust index if module ends up nested differently. No other line changes — `_BACKTEST_DIR / f'{strategy_version}-{ts}.json'` (line 121) consumes the new absolute path identically.

    2. `backtest/data_fetcher.py:24` — change:
       ```python
       _CACHE_DIR_DEFAULT = Path('.planning/backtests/data')
       ```
       to:
       ```python
       _PROJECT_ROOT = Path(__file__).resolve().parents[1]
       _CACHE_DIR_DEFAULT = _PROJECT_ROOT / '.planning' / 'backtests' / 'data'
       ```
       Line 132 consumer (`cache_dir if cache_dir is not None else _CACHE_DIR_DEFAULT`) is unchanged.

    3. `web/routes/backtest.py:45` — change:
       ```python
       _BACKTEST_DIR = Path('.planning/backtests')
       ```
       to:
       ```python
       _PROJECT_ROOT = Path(__file__).resolve().parents[2]
       _BACKTEST_DIR = _PROJECT_ROOT / '.planning' / 'backtests'
       ```
       Lines 59 + 76 (`backtest_dir = _BACKTEST_DIR`) are unchanged.

    Do NOT introduce a `paths.py` helper module (deferred per D-14/D-15 — premature centralisation).
  </action>
  <acceptance_criteria>
    - `grep -q "Path(__file__).resolve().parents" backtest/cli.py` returns 0 (matches found).
    - `grep -q "Path(__file__).resolve().parents" backtest/data_fetcher.py` returns 0.
    - `grep -q "Path(__file__).resolve().parents" web/routes/backtest.py` returns 0.
    - `grep -nE "= Path\\('\\.planning" backtest/cli.py backtest/data_fetcher.py web/routes/backtest.py` returns ZERO matches (no CWD-relative leftovers).
    - `python -c "import backtest.cli; print(backtest.cli._BACKTEST_DIR.is_absolute())"` prints `True`.
    - `python -c "from backtest.data_fetcher import _CACHE_DIR_DEFAULT; print(_CACHE_DIR_DEFAULT.is_absolute())"` prints `True`.
    - `python -c "from web.routes.backtest import _BACKTEST_DIR; print(_BACKTEST_DIR.is_absolute())"` prints `True`.
    - Each resolved path ends with `.planning/backtests` or `.planning/backtests/data` (visual check).
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && python -c "from backtest.cli import _BACKTEST_DIR; from backtest.data_fetcher import _CACHE_DIR_DEFAULT; from web.routes.backtest import _BACKTEST_DIR as W; assert _BACKTEST_DIR.is_absolute() and _CACHE_DIR_DEFAULT.is_absolute() and W.is_absolute(); assert _BACKTEST_DIR == W, (_BACKTEST_DIR, W); print('OK')"</automated>
  </verify>
  <done>All three modules anchor `.planning/backtests` paths via `Path(__file__).resolve().parents[N]`; resolved paths are absolute and identical between CLI and route module.</done>
</task>

<task type="auto">
  <name>Task 2: Subprocess regression test — CLI from /tmp and project root produces identical output paths</name>
  <files>tests/test_backtest_path_resolution.py</files>
  <read_first>
    - 29-CONTEXT.md §D-16 (subprocess-level test specification)
    - tests/test_backtest_cli.py (existing CLI test pattern reference)
    - ROADMAP SC-4 wording ("runs both from /tmp and asserts identical output paths")
  </read_first>
  <action>
    Create `tests/test_backtest_path_resolution.py` per D-16. The test:

    1. Resolves the project root via `Path(__file__).resolve().parents[1]`.
    2. Invokes `subprocess.run([sys.executable, '-m', 'backtest', '--years', '1'], cwd=<project_root>, capture_output=True, text=True, timeout=300, env={**os.environ, 'TSI_BACKTEST_OFFLINE': '1'})` IF such an env var / offline mode exists; OTHERWISE invokes a thin probe that imports `backtest.cli` and prints the resolved `_BACKTEST_DIR`. Use the import-probe approach to avoid a 5-year live yfinance pull in the test suite:

       ```python
       probe_cmd = [sys.executable, '-c', 'from backtest.cli import _BACKTEST_DIR; from backtest.data_fetcher import _CACHE_DIR_DEFAULT; from web.routes.backtest import _BACKTEST_DIR as W; print(_BACKTEST_DIR); print(_CACHE_DIR_DEFAULT); print(W)']
       ```

    3. Runs the probe twice: once with `cwd=PROJECT_ROOT`, once with `cwd='/tmp'`.
    4. Asserts stdout (3 path lines) is byte-identical between the two runs AND every line is an absolute path AND every line ends in `.planning/backtests` or `.planning/backtests/data`.

    Test class `TestBacktestPathCwdInvariance` with one test method `test_paths_identical_from_tmp_and_project_root`. Mark with `@pytest.mark.timeout(60)` if the project uses pytest-timeout; otherwise rely on the subprocess timeout argument.

    File MUST be ≤500 LOC (D-09 inherited from CLAUDE.md). Will be ~50 LOC.
  </action>
  <acceptance_criteria>
    - `test -f tests/test_backtest_path_resolution.py` succeeds.
    - `grep -q "subprocess.run" tests/test_backtest_path_resolution.py` succeeds.
    - `grep -q "/tmp" tests/test_backtest_path_resolution.py` succeeds.
    - `grep -q "TestBacktestPathCwdInvariance" tests/test_backtest_path_resolution.py` succeeds.
    - `pytest tests/test_backtest_path_resolution.py -x -q` returns rc=0.
    - Test asserts byte-identical stdout between `cwd=PROJECT_ROOT` and `cwd=/tmp` invocations.
  </acceptance_criteria>
  <verify>
    <automated>cd /Users/marcwiriadisastra/Documents/Work/Apps/trading-signals && .venv/bin/pytest tests/test_backtest_path_resolution.py -x -q</automated>
  </verify>
  <done>Subprocess regression test exists, passes, and proves CWD-invariance per D-16 + ROADMAP SC-4.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| filesystem | path resolution constants determine where backtest reports + cache parquet land |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-29-01-01 | Tampering | Path constants drift back to CWD-relative | mitigate | Subprocess CWD-invariance test asserts identical resolved paths from `/tmp` and project root every CI run |
| T-29-01-02 | Information Disclosure | `Path(__file__).resolve().parents[N]` could leak repo absolute path in logs | accept | Single-operator system; absolute path already appears in journalctl on droplet; no PII |
</threat_model>

<verification>
- `pytest tests/test_backtest_path_resolution.py -x -q` green.
- Full suite still green: `.venv/bin/pytest -q` returns rc=0.
- Manual smoke: `cd /tmp && python -m backtest --years 1` (or the import probe) writes/reads from `<project_root>/.planning/backtests/`, NOT `/tmp/.planning/backtests/`.
</verification>

<success_criteria>
ROADMAP SC-4 satisfied: `python -m backtest` and `/backtest` route resolve `.planning/backtests/` from project root regardless of caller CWD; subprocess regression test from `/tmp` and project root passes.
</success_criteria>

<output>
After completion, create `.planning/phases/29-v1-2-1-retroactive-patch-wrap-validation-sweep/29-01-SUMMARY.md`.
</output>