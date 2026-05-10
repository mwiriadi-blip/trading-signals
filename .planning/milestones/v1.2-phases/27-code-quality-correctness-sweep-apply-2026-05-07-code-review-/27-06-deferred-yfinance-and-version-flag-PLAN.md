---
phase: 27
plan: 06
type: execute
wave: 1A
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
    - "import yfinance is INSIDE the _get_yf() accessor, not at module top of data_fetcher.py."
    - "YFRateLimitError remains module-level (or re-exported from a stable location) so external `except YFRateLimitError` clauses don't break."
    - "python main.py --version prints STRATEGY_VERSION on stdout and exits 0."
    - "--version handling happens BEFORE importing heavy app modules (sys.argv check at top of main entrypoint)."
    - "Cold-start timing test asserts `import` time of app modules is short — does NOT use wall-clock <500ms (CI-flaky), but verifies yfinance NOT in sys.modules after `import data_fetcher`."
    - "Existing CLI surface (--once, --force-email, --reset, --test, etc.) unchanged."
  artifacts:
    - path: data_fetcher.py
      provides: "yfinance imported lazily via _get_yf() accessor"
      contains: "def _get_yf"
    - path: main.py
      provides: "--version flag handled before heavy imports"
      contains: "--version"
  key_links:
    - from: "main.py argparse"
      to: "system_params.STRATEGY_VERSION"
      via: "import + print"
      pattern: "STRATEGY_VERSION"
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave changed `1` → `1A`; depends_on remains empty.
- [x] M4 (cold-start <500ms flaky on CI) — replaced wall-clock <500ms assertion with `'yfinance' not in sys.modules after import data_fetcher` (subprocess-based for clean sys.modules). This is the actual semantic invariant; wall-clock is incidental and CI-dependent.
- [x] M4 (YFRateLimitError module-level) — keep YFRateLimitError importable at module level via lazy re-export in data_fetcher (not buried inside a function). External `except YFRateLimitError` clauses continue to work.
- [x] M4 (--version before heavy imports) — sys.argv check at top of main entrypoint BEFORE any app-module imports. Documented in action with explicit ordering.
- [x] M2 (doc rule) — SUMMARY artifact stays inside `.planning/phases/27-.../`.
- [x] Coordination with Plan 27-02 (HTTP_TIMEOUT_S) — _get_yf() accessor extended to also build a session with HTTP_TIMEOUT_S default (per Plan 27-02 agreed-6). Documented as cross-plan integration.

<objective>
Two cheap entry-point cleanups bundled (both ~10 lines):

1. **Deferred yfinance import (item #14):** move `import yfinance as yf` from data_fetcher.py top-level into a `_get_yf()` accessor function. Reduces cold-import time for `python main.py --version`, dashboard-only routes, mock-data tests. **YFRateLimitError stays module-level** (re-exported lazily) so external `except` clauses don't break.
2. **--version flag (item #17):** add `python main.py --version` → prints STRATEGY_VERSION → exits 0. **--version check happens BEFORE heavy app-module imports** (sys.argv inspection at the very top of main entrypoint).

Bundled because both touch entry-points and are individually too small (5 LOC each) to justify standalone plans. Total ≤ 15% context.

Purpose: faster cold start (#14) + GHA droplet-version assertion capability (#17).
Output: deferred import + module-level YFRateLimitError preserved + --version flag with early sys.argv check + 4 small regression tests.
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
#
# Plan refactor (review-fix M4 — preserve YFRateLimitError at module level):
#   - DELETE module-top `import yfinance as yf` and `from yfinance.exceptions import YFRateLimitError`.
#   - Define module-level lazy re-export pattern:
#       _yf = None
#       _yf_session = None
#       def _get_yf():
#         '''Lazy import + session config (Phase 27 #14).
#         Coordinates with Plan 27-02: session has HTTP_TIMEOUT_S default.'''
#         global _yf, _yf_session
#         if _yf is None:
#           import yfinance as yf
#           _yf = yf
#           import requests
#           from system_params import HTTP_TIMEOUT_S
#           s = requests.Session()
#           _orig = s.request
#           def _patched(method, url, **kwargs):
#             kwargs.setdefault('timeout', HTTP_TIMEOUT_S)
#             return _orig(method, url, **kwargs)
#           s.request = _patched
#           _yf_session = s
#         return _yf, _yf_session
#
#   - YFRateLimitError preservation: define as a module-level class that lazily proxies:
#       class YFRateLimitError(Exception):
#         '''Module-level re-export. Lazy-resolves to yfinance.exceptions.YFRateLimitError.'''
#         pass
#       def _get_yf_rate_limit_error():
#         from yfinance.exceptions import YFRateLimitError as _YFE
#         return _YFE
#     Internal `except` clauses use `_get_yf_rate_limit_error()`; external code that does
#     `from data_fetcher import YFRateLimitError` still gets a usable Exception class.
#     Caveat: if external code does `except yfinance.exceptions.YFRateLimitError`, that path
#     forces yfinance import — that's fine, it's the consumer's choice.
#
# main.py argparse + entrypoint (review-fix M4 — --version before heavy imports):
#   At the very top of `if __name__ == '__main__':` block (or main() entry):
#     import sys
#     if '--version' in sys.argv[1:]:
#       from system_params import STRATEGY_VERSION   # only system_params needed
#       print(STRATEGY_VERSION); sys.exit(0)
#   THEN argparse, validation, full app imports.
#   Keep argparse-side `--version` flag too for `--help` listing.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Deferred yfinance import via _get_yf() + preserved YFRateLimitError module-level</name>
  <read_first>
    - data_fetcher.py (full — 132 lines)
    - tests/test_data_fetcher.py (existing fixture / mock pattern)
    - any consumer of `from data_fetcher import YFRateLimitError` — grep: `grep -rn 'from data_fetcher import' --include='*.py'`
  </read_first>
  <behavior>
    - test_yfinance_not_imported_on_module_load: subprocess `python -c "import data_fetcher; import sys; assert 'yfinance' not in sys.modules"` succeeds.
    - test_yfinance_imported_on_first_fetch_call: subprocess `python -c "import data_fetcher; data_fetcher.fetch_canonical(...); import sys; assert 'yfinance' in sys.modules"` succeeds.
    - test_yfrate_limit_error_module_level_accessible: `from data_fetcher import YFRateLimitError` succeeds at module-import time WITHOUT triggering yfinance import.  <!-- review-fix: M4 -->
    - test_yfrate_limit_error_catchable: when fetch raises a real YFRateLimitError (mocked), `except YFRateLimitError as e:` (using the module-level proxy) catches it.
  </behavior>
  <action>
1. **data_fetcher.py — remove top-level imports:** delete `import yfinance as yf` and `from yfinance.exceptions import YFRateLimitError` from module-top.

2. **Add `_get_yf()` accessor + session config (per <interfaces>):** memoizes both yfinance module AND a configured Session. Integrates HTTP_TIMEOUT_S from Plan 27-02.

3. **Preserve YFRateLimitError at module level (review-fix M4):** define a lightweight Exception subclass at module top:
   ```python
   class YFRateLimitError(Exception):
     '''Phase 27 #14: module-level proxy for yfinance.exceptions.YFRateLimitError.
     Importable without forcing yfinance import.'''
     pass
   ```
   Internal `except` clauses use this proxy class (since we re-raise our own exception that wraps the yfinance one). When fetch_canonical catches the real yfinance.exceptions.YFRateLimitError (after _get_yf() loads yfinance), it converts/re-raises as `data_fetcher.YFRateLimitError`. External code `except YFRateLimitError` continues to work.

4. **Update fetch functions:** every body that uses yf calls `yf, session = _get_yf()`. Pass `session=session` to `yf.Ticker(...)` if 1.2.0 supports it (per Plan 27-02). If not, document in 27-DEBT.md.

5. **tests/test_deferred_yfinance_import.py (NEW):** 4 tests per behavior block. Use `subprocess.run` for clean sys.modules state.

6. Verify existing data_fetcher tests still green.
  </action>
  <verify>
    <automated>pytest tests/test_deferred_yfinance_import.py tests/test_data_fetcher.py -x -v</automated>
  </verify>
  <done>
    - `grep -c '^import yfinance\|^from yfinance' data_fetcher.py` == 0 (no module-top yfinance).
    - YFRateLimitError module-level class defined.
    - 4 tests in test_deferred_yfinance_import.py green (incl. YFRateLimitError module-level accessibility).
    - Existing data_fetcher tests still green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: --version flag with early sys.argv check (before heavy imports)</name>
  <read_first>
    - main.py lines 1-30 (top of file — for the early sys.argv hook)
    - main.py lines 730-810 (_build_parser + _validate_flag_combo)
    - main.py lines 1880-1995 (main() body + __main__ block)
    - system_params.py (STRATEGY_VERSION location)
  </read_first>
  <behavior>
    - test_version_flag_prints_strategy_version: subprocess.run([sys.executable, 'main.py', '--version']) returns rc=0, stdout==STRATEGY_VERSION+'\n'.
    - test_version_flag_does_not_load_yfinance: subprocess `python main.py --version` — yfinance NOT in sys.modules of the subprocess. Verifies the early sys.argv check works (no heavy imports triggered).  <!-- review-fix: M4 -->
    - test_version_flag_does_not_trigger_other_paths: stdout must NOT contain 'Daily run' or any other run-output text.
    - test_version_flag_argparse_help_lists_it: `python main.py --help` mentions `--version` (argparse-side flag still registered for help).
  </behavior>
  <action>
1. **main.py — early sys.argv check (review-fix M4):** at the very top of the `if __name__ == '__main__':` block, BEFORE any app-module imports (`from data_fetcher import ...`, etc.):
   ```python
   if __name__ == '__main__':
     import sys
     if '--version' in sys.argv[1:]:
       from system_params import STRATEGY_VERSION
       print(STRATEGY_VERSION)
       sys.exit(0)
     # ... existing main() invocation
   ```

2. **main.py _build_parser:** ALSO add `p.add_argument('--version', action='store_true', help='print STRATEGY_VERSION and exit 0')`. This keeps `--help` correct. The argparse-side handler is a fallback (if main() is called from tests with argv=['--version'], it routes via this handler).

3. **main.py main(argv):** at the top after `args = parser.parse_args(argv)`:
   ```python
   if getattr(args, 'version', False):
     from system_params import STRATEGY_VERSION
     print(STRATEGY_VERSION)
     return 0
   ```
   This handles the test-import path (where `__main__` block doesn't run).

4. **tests/test_version_flag.py (NEW):** 4 tests per behavior block. Use subprocess for the yfinance-not-imported test.

5. Run `pytest tests/test_version_flag.py -x -v`.
  </action>
  <verify>
    <automated>pytest tests/test_version_flag.py -x -v</automated>
  </verify>
  <done>
    - `python main.py --version` prints e.g. `v1.2.0` and exits 0.
    - yfinance not imported on --version path (subprocess assertion).
    - 4 tests in test_version_flag.py green.
    - Existing main.py tests (test_main.py / test_scheduler.py) still green.
    - argparse `--help` lists `--version`.
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
python -c "import sys; import main; assert 'yfinance' not in sys.modules"   # smoke check
pytest -x                       # full suite
```
</verification>

<success_criteria>
- yfinance import deferred via _get_yf() accessor; YFRateLimitError module-level preserved.
- python main.py --version handled BEFORE heavy app imports (early sys.argv check).
- 8 new tests across 2 files green (including the no-yfinance-on-version-path assertion).
- No regression in existing main / data_fetcher tests.
</success_criteria>

<output>
Create `27-06-SUMMARY.md` with: _get_yf() accessor implementation, YFRateLimitError preservation strategy, --version early-check ordering (sys.argv hook + argparse-side), no-wall-clock semantic test pattern.
</output>
