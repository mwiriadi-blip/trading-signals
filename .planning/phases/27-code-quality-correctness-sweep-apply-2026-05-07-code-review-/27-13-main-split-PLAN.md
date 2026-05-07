---
phase: 27
plan: 13
type: execute
wave: 3
parallel: false  # <!-- review-fix: agreed-1 — Wave 3 sequential -->
depends_on:
  - 27-12-notifier-split-PLAN.md  # <!-- review-fix: agreed-1 — sequential 27-12 → 27-13 -->
  - 27-06-deferred-yfinance-and-version-flag-PLAN.md
  - 27-07-naive-datetime-and-migration-contiguity-PLAN.md
  - 27-09-signal-shape-unification-PLAN.md
  - 27-10-warnings-fifo-rundate-lookahead-tests-PLAN.md
  - 27-11-crash-email-fallback-PLAN.md
files_modified:
  - main.py
  - daily_loop.py        # <!-- review-fix: agreed-2 — orchestration only, <500 LOC -->
  - daily_run.py         # <!-- review-fix: agreed-2 — NEW: run_daily_check body + helpers -->
  - state_actions.py     # <!-- review-fix: agreed-2 — NEW: _handle_reset + _LAST_LOADED_STATE getter/setter -->
  - crash_boundary.py    # <!-- review-fix: agreed-2 — NEW: _send_crash_email + _build_crash_state_summary + _dispatch_email_and_maintain_warnings -->
  - cli_parser.py
  - interactive.py
  - scheduler_driver.py
  - tests/test_main_split_seam.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "main.py becomes a thin <150 LOC entry+re-export shim."
    - "Each new module <500 LOC: daily_loop.py (orchestration), daily_run.py (run_daily_check), state_actions.py (_handle_reset + _LAST_LOADED_STATE), crash_boundary.py (_send_crash_email + _build_crash_state_summary + _dispatch_email_and_maintain_warnings), cli_parser.py, interactive.py, scheduler_driver.py."
    - "_dispatch_email_and_maintain_warnings RELOCATES to crash_boundary.py per Plan 27-12 agreed-3 (was at main.py:1638)."
    - "Module-level monkeypatch targets preserved: main.data_fetcher, main.signal_engine, main.logging — all re-exportable from main.py shim."
    - "python main.py CLI surface unchanged: --once, --version, --reset, --test, --force-email, --initial-account, all interactive Q&A."
    - "Droplet systemd unit + GHA workflow_dispatch need ZERO changes."
    - "tests/test_main.py + tests/test_scheduler.py pass without test changes (Option A re-export shim)."
  artifacts:
    - path: main.py
      provides: "thin entry-point: argparse + dispatch + early --version + re-export shim"
      contains: "if __name__ == '__main__'"
    - path: daily_loop.py
      provides: "orchestration only: imports + delegates to daily_run / state_actions / crash_boundary"
      contains: "from daily_run"
    - path: daily_run.py
      provides: "run_daily_check + _run_daily_check_caught body + helpers"
      contains: "run_daily_check"
    - path: state_actions.py
      provides: "_handle_reset + _LAST_LOADED_STATE getter/setter (singleton-preserving)"
      contains: "_LAST_LOADED_STATE"
    - path: crash_boundary.py
      provides: "_send_crash_email + _build_crash_state_summary + _dispatch_email_and_maintain_warnings"
      contains: "_send_crash_email"
    - path: cli_parser.py
      provides: "_build_parser + _validate_flag_combo + _mode_label"
      contains: "_build_parser"
    - path: interactive.py
      provides: "interactive Q&A path"
      contains: "input"
    - path: scheduler_driver.py
      provides: "schedule library wiring + _FakeScheduler + _get_process_tzname"
      contains: "schedule"
  key_links:
    - from: "main.py"
      to: "daily_loop.run_daily_check"
      via: "import + dispatch"
      pattern: "from daily_loop import"
    - from: "daily_loop.py"
      to: "daily_run / state_actions / crash_boundary"
      via: "delegate"
      pattern: "from (daily_run|state_actions|crash_boundary)"
---

## Review fixes applied

- [x] agreed-1 (wave/dependency rebuild) — wave 3 SEQUENTIAL after 27-12; depends_on=[27-12, 27-06, 27-07, 27-09, 27-10, 27-11] explicit.
- [x] agreed-2 (Codex HIGH overweight + OpenCode HIGH missing assignments) — daily_loop.py was estimated ~700 LOC contradicting <500 budget. Split into THREE smaller seams:
  - `daily_loop.py` (orchestration only) — imports + delegates
  - `daily_run.py` (run_daily_check body + helpers)
  - `state_actions.py` (_handle_reset + _LAST_LOADED_STATE)
  - `crash_boundary.py` (_send_crash_email + _build_crash_state_summary + _dispatch_email_and_maintain_warnings)
- [x] agreed-2 (function-ownership table) — explicit `<function_ownership>` block listing every public/private function being moved and its new home.
- [x] agreed-3 (Plan 27-12 deferred _dispatch_email_and_maintain_warnings) — function relocates HERE to crash_boundary.py.
- [x] agreed-2 (re-export shim manifest for main.data_fetcher etc.) — explicit re-export of `data_fetcher`, `signal_engine`, `logging` modules in main.py shim so monkeypatch paths continue to work.
- [x] M1 (brittle implementation tests) — LOC tests use ±10% tolerance and "no module exceeds 500" gate (not "exactly < 500" rigidity).
- [x] M2 (doc rule) — manifest stays inside `.planning/phases/27-.../`.
- [x] revision warning-2 — Task 2 split into Task 2a (cli_parser.py + scheduler_driver.py — low-dep seams) and Task 2b (daily_run.py + state_actions.py + crash_boundary.py + daily_loop.py — inter-dep seams + final shim). Total scope identical; execution sequence safer. `pytest -x` runs between 2a and 2b.

<objective>
Split main.py (1996 LOC) along SEVEN seams: cli_parser / daily_loop (orchestration) / daily_run / state_actions / crash_boundary / interactive / scheduler_driver. main.py becomes a thin entry-point + re-export shim. Public CLI surface unchanged.

Sequenced AFTER 27-12 (which deferred `_dispatch_email_and_maintain_warnings` here per agreed-3) and after Wave 1-2 functional changes. Splitting before functional changes would force re-rebasing each functional patch.

**Critical correction (review-fix agreed-2):** original plan's daily_loop.py was estimated ~700 LOC, contradicting the <500 budget. Split into:
1. `daily_loop.py` — pure orchestration (imports + delegate calls). ~80 LOC.
2. `daily_run.py` — `run_daily_check`, `_run_daily_check_caught`, fetch/sizing/signal helpers. ~400 LOC.
3. `state_actions.py` — `_handle_reset`, `_LAST_LOADED_STATE` getter/setter (preserves singleton). ~150 LOC.
4. `crash_boundary.py` — `_send_crash_email`, `_build_crash_state_summary`, `_dispatch_email_and_maintain_warnings`. ~250 LOC.

**Module-level monkeypatch preservation (review-fix agreed-2):** tests reference `main.data_fetcher`, `main.signal_engine`, `main.logging` (module-level attributes — typically the underlying imported module objects). main.py shim must re-export these:
```python
import data_fetcher           # tests: main.data_fetcher
import signal_engine          # tests: main.signal_engine
import logging                # tests: main.logging.basicConfig
```

Purpose: file-size hygiene (review item #3).
Output: 7 new modules + thin main.py + parity tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@main.py

<function_ownership>
<!-- review-fix: agreed-2 — explicit function-ownership table -->

| main.py function/global (current location) | New file | LOC estimate |
|---|---|---|
| `_build_parser` | cli_parser.py | ~120 |
| `_validate_flag_combo` | cli_parser.py | ~80 |
| `_mode_label` | cli_parser.py | ~20 |
| `run_daily_check` (body) | daily_run.py | ~250 |
| `_run_daily_check_caught` | daily_run.py | ~80 |
| any `_fetch_*` / `_compute_*` helpers used only by run_daily_check | daily_run.py | ~70 |
| `_LAST_LOADED_STATE` (module-level global) | state_actions.py | (single ref) |
| `_get_last_loaded_state()` / `_set_last_loaded_state()` accessors | state_actions.py | ~30 |
| `_handle_reset` | state_actions.py | ~120 |
| `_send_crash_email` (line 454) | crash_boundary.py | ~120 |
| `_build_crash_state_summary` | crash_boundary.py | ~80 |
| `_dispatch_email_and_maintain_warnings` (line 1638, deferred from 27-12) | crash_boundary.py | ~50 |
| `interactive_*` Q&A path | interactive.py | ~250 |
| `_FakeScheduler` | scheduler_driver.py | ~80 |
| `_get_process_tzname` | scheduler_driver.py | ~30 |
| schedule library wiring (start_daemon etc.) | scheduler_driver.py | ~140 |
| daily_loop.py | NEW — pure orchestration | ~80 |
| main.py | thin entry + re-export shim | <150 |

**Re-export manifest (main.py shim — review-fix agreed-2):**
```python
# Tests do `monkeypatch.setattr('main.data_fetcher.fetch_canonical', ...)` etc.
# These imports re-export the module objects so the patched-attribute path works.
import data_fetcher        # main.data_fetcher
import signal_engine       # main.signal_engine
import logging             # main.logging
import sys                 # main.sys (if used)
# Symbol re-exports
from cli_parser import _build_parser, _validate_flag_combo, _mode_label
from daily_run import run_daily_check, _run_daily_check_caught
from state_actions import _handle_reset, _get_last_loaded_state, _set_last_loaded_state
from crash_boundary import (_send_crash_email, _build_crash_state_summary,
                             _dispatch_email_and_maintain_warnings)
from interactive import interactive_q_and_a   # adjust to actual public name
from scheduler_driver import _FakeScheduler, _get_process_tzname
# Backwards-compat: the old global _LAST_LOADED_STATE is now an accessor pair, but tests
# that read `main._LAST_LOADED_STATE` need a property-like shim:
class _LastLoadedStateProxy:
  def __get__(self, *a): return _get_last_loaded_state()
  def __set__(self, _, v): _set_last_loaded_state(v)
# OR simpler: expose as module attribute that's lazily resolved:
def __getattr__(name):
  if name == '_LAST_LOADED_STATE': return _get_last_loaded_state()
  raise AttributeError(name)
```
</function_ownership>

<interfaces>
# _LAST_LOADED_STATE invariant (preserved per agreed-2):
#   Single singleton across the daemon. Lives in state_actions.py.
#   Accessor pair: _get_last_loaded_state() / _set_last_loaded_state(s)
#   main.py uses module-level __getattr__ to resolve `main._LAST_LOADED_STATE` → accessor call.
#
# Public CLI surface unchanged. ExecStart=python main.py works as before.
#
# Test-import-parity strategy: Option A — main.py re-exports every helper test_main.py /
# test_scheduler.py reference. Plus re-exports `data_fetcher`, `signal_engine`, `logging`
# module objects so monkeypatch paths work.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Inventory main.py — manifest with full function-ownership table</name>
  <read_first>
    - main.py (full — read in chunks of ~500 LOC)
    - tests/test_main.py
    - tests/test_scheduler.py
  </read_first>
  <action>
1. Read main.py in chunks. Validate the function_ownership table against actual code; adjust any LOC estimates.

2. Capture test-side public API:
   ```bash
   grep -nE 'main\.[a-zA-Z_]|from main import|monkeypatch\..*main' tests/test_main.py tests/test_scheduler.py
   ```
   Each name + module-level attribute is a shim re-export.

3. Verify module-level imports in tests: explicitly note `main.data_fetcher`, `main.signal_engine`, `main.logging` patterns. These need module re-exports in shim, not just symbol re-exports.

4. Write manifest at `.planning/phases/27-.../main-split-manifest.md` with:
   - line range → target seam
   - re-export list (symbols AND modules)
   - cross-module edges (acyclic check)
   - _LAST_LOADED_STATE accessor strategy

5. Verify _LAST_LOADED_STATE invariant: lives ONLY in state_actions.py.
  </action>
  <verify>
    <automated>test -f .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/main-split-manifest.md</automated>
  </verify>
  <done>
    - Manifest written with function-ownership table validated.
    - Module + symbol re-export surfaces enumerated.
    - No circular imports.
    - _LAST_LOADED_STATE accessor strategy chosen.
  </done>
</task>

<task type="auto">
  <name>Task 2a: Create low-dependency seams (cli_parser.py + scheduler_driver.py)</name>
  <!-- revision-fix: warning-2 — Task 2 split into 2a/2b for safer execution; total scope unchanged -->
  <read_first>
    - manifest from Task 1
    - main.py — sections owning _build_parser / _validate_flag_combo / _mode_label / _FakeScheduler / _get_process_tzname / schedule wiring
  </read_first>
  <action>
1. Create `cli_parser.py` and `scheduler_driver.py` (the two seams with the FEWEST cross-dependencies — they don't share function moves with daily_run/state_actions/crash_boundary).

2. **cli_parser.py:** move `_build_parser`, `_validate_flag_combo`, `_mode_label` per function_ownership table. Preserve docstrings, Phase-tag comments.

3. **scheduler_driver.py:** move `_FakeScheduler`, `_get_process_tzname`, schedule library wiring (start_daemon etc.) per function_ownership table.

4. **Do NOT yet** delete the moved code from main.py — keep both old and new copies temporarily so main.py still imports successfully. (We'll prune in 2b once daily_run/state_actions/crash_boundary land and the shim form is finalised.)

5. Add temporary stub re-exports at the top of main.py so existing call-sites keep working:
   ```python
   from cli_parser import _build_parser, _validate_flag_combo, _mode_label  # noqa: F401
   from scheduler_driver import _FakeScheduler, _get_process_tzname  # noqa: F401
   ```

6. Run `pytest -x` — MUST pass. If a test imports `main._build_parser` etc., the new shim line keeps it working.

7. Sanity: `python main.py --version`, `python main.py --help`.
  </action>
  <verify>
    <automated>pytest -x && python main.py --version</automated>
  </verify>
  <done>
    - cli_parser.py and scheduler_driver.py exist; each <500 LOC (±10%).
    - main.py imports + re-exports them.
    - Full suite green.
    - python main.py --version + --help work.
  </done>
</task>

<task type="auto">
  <name>Task 2b: Create inter-dependent seams (daily_run + state_actions + crash_boundary + daily_loop) + final main.py shim</name>
  <!-- revision-fix: warning-2 — second half of split; these four seams share function moves and re-export shim -->
  <read_first>
    - manifest from Task 1
    - main.py (post 2a — old run_daily_check / _handle_reset / _send_crash_email / _dispatch_email_and_maintain_warnings still present)
    - cli_parser.py + scheduler_driver.py (from 2a — already landed)
  </read_first>
  <action>
1. Create `daily_run.py`, `state_actions.py`, `crash_boundary.py`, `daily_loop.py` (the four inter-dependent seams).

2. Move functions per function_ownership table. Preserve docstrings, Phase-tag comments.

3. **state_actions.py:** _LAST_LOADED_STATE module-level + accessor pair:
   ```python
   _LAST_LOADED_STATE: dict | None = None
   def _get_last_loaded_state(): return _LAST_LOADED_STATE
   def _set_last_loaded_state(s):
     global _LAST_LOADED_STATE
     _LAST_LOADED_STATE = s
   ```
   All consumers (run_daily_check, _send_crash_email) use these accessors — never import `_LAST_LOADED_STATE` by value (would break singleton).

4. **daily_loop.py (orchestration only):** thin module that imports + delegates:
   ```python
   '''Orchestration layer. Delegates to daily_run / state_actions / crash_boundary.'''
   from daily_run import run_daily_check, _run_daily_check_caught
   from state_actions import _handle_reset, _get_last_loaded_state, _set_last_loaded_state
   from crash_boundary import _send_crash_email, _dispatch_email_and_maintain_warnings
   ```

5. **crash_boundary.py:** receives `_dispatch_email_and_maintain_warnings` (deferred from 27-12 per agreed-3). Imports from notifier package: `from notifier import send_email, _write_last_crash, enforce_fifo_bound`.

6. **main.py — thin entry + re-export shim** (final form, supersedes 2a's interim shim):
   ```python
   '''Trading Signals — entry point. Phase 27 #3 split.'''
   import sys
   # Early --version (Plan 27-06)
   if __name__ == '__main__' and '--version' in sys.argv[1:]:
     from system_params import STRATEGY_VERSION
     print(STRATEGY_VERSION); sys.exit(0)
   # Module re-exports (preserve monkeypatch paths) — review-fix agreed-2
   import data_fetcher           # main.data_fetcher
   import signal_engine          # main.signal_engine
   import logging                # main.logging
   # Symbol re-exports
   from cli_parser import _build_parser, _validate_flag_combo, _mode_label  # noqa: F401
   from daily_run import run_daily_check, _run_daily_check_caught  # noqa: F401
   from state_actions import _handle_reset, _get_last_loaded_state, _set_last_loaded_state  # noqa: F401
   from crash_boundary import (_send_crash_email, _build_crash_state_summary,  # noqa: F401
                                _dispatch_email_and_maintain_warnings)
   from interactive import interactive_q_and_a  # noqa: F401 — adjust to actual name
   from scheduler_driver import _FakeScheduler, _get_process_tzname  # noqa: F401
   from system_params import STRATEGY_VERSION
   def __getattr__(name):
     '''review-fix agreed-2: lazy proxy for _LAST_LOADED_STATE so tests reading main._LAST_LOADED_STATE work.'''
     if name == '_LAST_LOADED_STATE': return _get_last_loaded_state()
     raise AttributeError(f'module main has no attribute {name!r}')
   def main(argv: list[str] | None = None) -> int:
     parser = _build_parser()
     args = parser.parse_args(argv)
     if getattr(args, 'version', False):
       print(STRATEGY_VERSION); return 0
     _validate_flag_combo(args, parser)
     return _dispatch(args)
   def _dispatch(args) -> int:
     # ~30 LOC: route --reset / --test / --force-email / --once / daemon to the right module.
     ...
   if __name__ == '__main__':
     sys.exit(main())
   ```
   Now PRUNE the original function bodies from main.py (they live in the new modules). main.py shrinks to <150 LOC.

7. Create `interactive.py` if not yet present (Task 1 manifest shows it as a separate file; move interactive Q&A path here).

8. Run `pytest tests/test_main.py tests/test_scheduler.py -x` — MUST pass unchanged.

9. Run full `pytest -x`.

10. Sanity:
    ```
    python main.py --version
    python main.py --help
    wc -l main.py daily_loop.py daily_run.py state_actions.py crash_boundary.py cli_parser.py interactive.py scheduler_driver.py
    ```
  </action>
  <verify>
    <automated>pytest tests/test_main.py tests/test_scheduler.py -x</automated>
  </verify>
  <done>
    - 7 new modules created (4 from 2b + 2 from 2a + interactive.py).
    - main.py <150 LOC; each new module <500 LOC (±10% per M1).
    - test_main.py + test_scheduler.py green without changes.
    - Full suite green.
    - python main.py --version + --help work.
    - main.data_fetcher / main.signal_engine / main.logging accessible (monkeypatch paths preserved).
    - main._LAST_LOADED_STATE works via __getattr__ proxy.
  </done>
</task>

<task type="auto">
  <name>Task 3: Parity test — CLI surface + re-exports + module monkeypatch targets</name>
  <read_first>
    - main.py (post-split)
  </read_first>
  <action>
1. **tests/test_main_split_seam.py (NEW):**
   ```python
   import subprocess, sys, pathlib

   def test_main_py_is_thin():
     loc = pathlib.Path('main.py').read_text().count('\n')
     assert loc < 200, f'main.py exceeded thin shim budget: {loc}'

   def test_cli_version_works():
     r = subprocess.run([sys.executable, 'main.py', '--version'], capture_output=True, text=True)
     assert r.returncode == 0
     assert r.stdout.strip().startswith('v')

   def test_cli_help_works():
     r = subprocess.run([sys.executable, 'main.py', '--help'], capture_output=True, text=True)
     assert r.returncode == 0
     assert '--once' in r.stdout
     assert '--version' in r.stdout

   def test_main_re_exports_symbols():
     import main
     for name in ['_build_parser', 'run_daily_check', '_handle_reset',
                  '_FakeScheduler', '_get_process_tzname',
                  '_send_crash_email', '_build_crash_state_summary',
                  '_dispatch_email_and_maintain_warnings']:   # review-fix agreed-3
       assert hasattr(main, name), f'{name} missing from main.py shim'

   def test_main_re_exports_modules():
     '''review-fix agreed-2: main.data_fetcher / main.signal_engine / main.logging preserved.'''
     import main
     assert hasattr(main, 'data_fetcher')
     assert hasattr(main, 'signal_engine')
     assert hasattr(main, 'logging')

   def test_last_loaded_state_proxy_works():
     '''review-fix agreed-2: main._LAST_LOADED_STATE accessible via __getattr__ proxy.'''
     import main, state_actions
     state_actions._set_last_loaded_state({'test': 'value'})
     assert main._LAST_LOADED_STATE == {'test': 'value'}

   def test_new_modules_under_500_loc():
     for f in ['cli_parser.py','daily_loop.py','daily_run.py','state_actions.py',
               'crash_boundary.py','interactive.py','scheduler_driver.py']:
       loc = pathlib.Path(f).read_text().count('\n')
       assert loc < 550, f'{f} exceeded LOC budget: {loc}'   # ±10% tolerance per M1
   ```
  </action>
  <verify>
    <automated>pytest tests/test_main_split_seam.py -x -v</automated>
  </verify>
  <done>7 parity tests green.</done>
</task>

</tasks>

<threat_model>
N/A — pure code reorganisation.
</threat_model>

<verification>
```
pytest tests/test_main.py tests/test_scheduler.py tests/test_main_split_seam.py -x
wc -l main.py daily_loop.py daily_run.py state_actions.py crash_boundary.py cli_parser.py interactive.py scheduler_driver.py
python main.py --version
python main.py --help
pytest -x   # full suite
```
</verification>

<success_criteria>
- main.py <150 LOC; daily_loop / daily_run / state_actions / crash_boundary / cli_parser / interactive / scheduler_driver each <500 LOC (±10%).
- _dispatch_email_and_maintain_warnings now in crash_boundary.py (relocated from main.py:1638 per agreed-3).
- Module re-exports (data_fetcher, signal_engine, logging) preserved in main.py shim.
- _LAST_LOADED_STATE singleton preserved via __getattr__ proxy + accessor pair.
- Public CLI surface unchanged.
- tests/test_main.py + tests/test_scheduler.py pass unchanged.
- 7 new parity tests green.
</success_criteria>

<output>
Create `27-13-SUMMARY.md` with: function-ownership table actual line counts, manifest summary, line counts before/after for all 7 new modules, re-export list (symbols + modules), parity test results, _LAST_LOADED_STATE accessor strategy outcome.
</output>
