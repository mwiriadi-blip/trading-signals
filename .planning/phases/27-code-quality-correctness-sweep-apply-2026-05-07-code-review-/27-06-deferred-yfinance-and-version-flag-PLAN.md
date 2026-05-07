---
phase: 27
plan: 06
type: execute
wave: 1
parallel: true
depends_on: []
files_modified:
  - data_fetcher.py
  - main.py
  - tests/test_version_flag.py
  - tests/test_deferred_yfinance_import.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "import yfinance is INSIDE the fetch function, not at module top of data_fetcher.py."
    - "python main.py --version prints STRATEGY_VERSION on stdout and exits 0."
    - "python main.py --version completes in <500ms cold (no yfinance import on this path)."
    - "Existing CLI surface (--once, --force-email, --reset, --test, etc.) unchanged."
  artifacts:
    - path: data_fetcher.py
      provides: "yfinance imported lazily"
      contains: "def fetch"
    - path: main.py
      provides: "--version flag"
      contains: "--version"
  key_links:
    - from: "main.py argparse"
      to: "system_params.STRATEGY_VERSION"
      via: "import + print"
      pattern: "STRATEGY_VERSION"
---

<objective>
Two cheap entry-point cleanups bundled (both ~10 lines):

1. **Deferred yfinance import (item #14):** move `import yfinance as yf` from data_fetcher.py top-level into the function body that actually fetches. Reduces cold-import time for `python main.py --version`, dashboard-only routes, mock-data tests.
2. **--version flag (item #17):** add `python main.py --version` → prints STRATEGY_VERSION → exits 0.

Bundled because both touch entry-points and are individually too small (5 LOC each) to justify standalone plans. Total ≤ 15% context.

Purpose: faster cold start (#14) + GHA droplet-version assertion capability (#17).
Output: deferred import + --version flag + 2 small regression tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@data_fetcher.py
@main.py
@system_params.py

<interfaces>
# data_fetcher.py current top-level imports (lines 26-32):
#   import logging
#   import time
#   import pandas as pd
#   import requests.exceptions
#   import yfinance as yf
#   from yfinance.exceptions import YFRateLimitError
# Move BOTH yfinance imports to inside `fetch_*` function.
# Keep `requests.exceptions` top-level — it's stdlib-fast.
# Keep `pd` top-level — pandas is unavoidable for return-type annotations and other module-level usage.
#
# main.py argparse (line 730 `_build_parser`):
#   - Add p.add_argument('--version', action='store_true', help='print STRATEGY_VERSION and exit 0')
#   - Inside main(argv): if args.version: print(STRATEGY_VERSION); return 0  (handle BEFORE _validate_flag_combo so it doesn't trip the mutually-exclusive groups)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Deferred yfinance import + cold-start regression test</name>
  <read_first>
    - data_fetcher.py (full — 132 lines)
    - tests/test_data_fetcher.py (existing fixture / mock pattern)
  </read_first>
  <behavior>
    - test_yfinance_not_imported_on_module_load: `import data_fetcher` does NOT import yfinance (assert 'yfinance' NOT in sys.modules after the import — caveat: must run in subprocess to get a clean sys.modules).
    - test_yfinance_imported_on_first_fetch_call: after calling data_fetcher.fetch_*(...), 'yfinance' IS in sys.modules.
    - Use `subprocess.run([sys.executable, '-c', '...'], capture_output=True)` to isolate sys.modules state.
  </behavior>
  <action>
1. **data_fetcher.py:** delete lines `import yfinance as yf` and `from yfinance.exceptions import YFRateLimitError` from the module-top imports.
2. Inside the function that actually fetches (likely `fetch_canonical_data` or similar — read the file to find the entry point), add at the top of the function body:
   ```python
   import yfinance as yf
   from yfinance.exceptions import YFRateLimitError
   ```
3. If multiple functions use yfinance, choose the option that keeps the import lazy:
   - **Option A (most eloquent):** define a private `_get_yf()` accessor at module scope that imports on first call and memoizes. Functions call `yf = _get_yf()`. One import site, multiple consumers.
   - **Option B (simpler):** repeat the local import in every consumer function. More duplication but zero shared state.
   > **Most eloquent:** Option A — single import site, locality of the lazy-load decision is in `_get_yf` not scattered. Use Option A.
4. **tests/test_deferred_yfinance_import.py (NEW):** 2 tests per behavior block.
5. Verify existing data_fetcher tests still green.
  </action>
  <verify>
    <automated>pytest tests/test_deferred_yfinance_import.py tests/test_data_fetcher.py -x -v</automated>
  </verify>
  <done>
    - `grep -c '^import yfinance\|^from yfinance' data_fetcher.py` == 0 (top-level), all imports are inside function bodies.
    - 2 tests in test_deferred_yfinance_import.py green.
    - Existing data_fetcher tests still green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: --version flag</name>
  <read_first>
    - main.py lines 730-810 (_build_parser + _validate_flag_combo)
    - main.py lines 1880-1995 (main() body + __main__ block)
    - system_params.py (STRATEGY_VERSION constant location)
  </read_first>
  <behavior>
    - test_version_flag_prints_strategy_version: subprocess.run([sys.executable, 'main.py', '--version']) returns rc=0, stdout=='v1.2.0\n' (or whatever STRATEGY_VERSION is at test time — read it from system_params).
    - test_version_flag_does_not_trigger_other_paths: stdout must NOT contain 'Daily run' or any other run-output text — i.e. version-handler short-circuits before _validate_flag_combo and before the daily-loop path.
    - test_version_flag_cold_start_time: subprocess.run finishes in <500ms wall-clock (yfinance NOT imported on this path because data_fetcher's import is deferred — implicit dependency on Task 1, but since both are in this plan, fine).
  </behavior>
  <action>
1. **main.py _build_parser:** add `p.add_argument('--version', action='store_true', help='print STRATEGY_VERSION and exit 0')`.
2. **main.py main(argv):** at the very top after `args = parser.parse_args(argv)`, BEFORE `_validate_flag_combo`:
   ```python
   if getattr(args, 'version', False):
     from system_params import STRATEGY_VERSION
     print(STRATEGY_VERSION)
     return 0
   ```
3. **tests/test_version_flag.py (NEW):** 3 tests per behavior block. Use subprocess to get true-cold-start measurement.
4. Run `pytest tests/test_version_flag.py -x -v`.
  </action>
  <verify>
    <automated>pytest tests/test_version_flag.py -x -v</automated>
  </verify>
  <done>
    - `python main.py --version` prints e.g. `v1.2.0` and exits 0.
    - 3 tests in test_version_flag.py green.
    - Existing main.py tests (test_main.py / test_scheduler.py) still green.
  </done>
</task>

</tasks>

<threat_model>
N/A — no security-relevant surface touched. --version is read-only print; deferred yfinance import is performance-only.
</threat_model>

<verification>
```
pytest tests/test_version_flag.py tests/test_deferred_yfinance_import.py -x -v
python main.py --version       # prints version, exits 0
time python main.py --version  # <500ms cold (smoke check)
pytest -x                       # full suite
```
</verification>

<success_criteria>
- yfinance import deferred (zero top-level yfinance imports in data_fetcher.py).
- python main.py --version works as specified.
- 5 new tests across 2 files green.
- No regression in existing main / data_fetcher tests.
</success_criteria>

<output>
Create `27-06-SUMMARY.md` with: deferred-import implementation choice (Option A vs B), --version code change diff, cold-start time measurement.
</output>
