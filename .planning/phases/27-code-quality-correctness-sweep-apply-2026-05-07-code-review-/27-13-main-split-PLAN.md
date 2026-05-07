---
phase: 27
plan: 13
type: execute
wave: 3
parallel: true
depends_on:
  - 27-06-deferred-yfinance-and-version-flag-PLAN.md
  - 27-07-naive-datetime-and-migration-contiguity-PLAN.md
  - 27-09-signal-shape-unification-PLAN.md
  - 27-10-warnings-fifo-rundate-lookahead-tests-PLAN.md
  - 27-11-crash-email-fallback-PLAN.md
files_modified:
  - main.py
  - daily_loop.py
  - cli_parser.py
  - interactive.py
  - scheduler_driver.py
  - tests/test_main_split_seam.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "main.py becomes a thin <150 LOC entry+re-export shim."
    - "Each new module <500 LOC."
    - "python main.py CLI surface unchanged: --once, --version, --reset, --test, --force-email, --initial-account, all interactive Q&A paths work identically."
    - "Droplet systemd unit (ExecStart=.../python main.py) needs ZERO changes."
    - "GHA workflow_dispatch path needs ZERO changes."
    - "tests/test_main.py + tests/test_scheduler.py pass without test changes (Option A re-export shim)."
  artifacts:
    - path: main.py
      provides: "thin entry-point: argparse + dispatch + crash boundary + re-export shim"
      contains: "if __name__ == '__main__'"
    - path: daily_loop.py
      provides: "run_daily_check + _LAST_LOADED_STATE + _handle_reset"
      contains: "run_daily_check"
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
---

<objective>
Split main.py (1996 LOC) along four seams: cli_parser / daily_loop / interactive / scheduler_driver. main.py becomes a thin entry-point + re-export shim. Public CLI surface unchanged.

Sequenced LAST in Wave 3 so all functional changes from earlier plans (--version flag, run-date INFO log, deferred yfinance, dict-shape signals migrator wiring) land BEFORE the split. Splitting before functional changes would force re-rebasing each functional patch.

Purpose: file-size hygiene (review item #3).
Output: 4 new modules + thin main.py + parity tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@main.py

<interfaces>
# Proposed seams (read main.py and adjust to actual structure):
#   cli_parser.py          ~250 LOC  — _build_parser, _validate_flag_combo, _mode_label
#   daily_loop.py          ~700 LOC  — run_daily_check, _run_daily_check_caught,
#                                       _LAST_LOADED_STATE module-level cache, _handle_reset
#   interactive.py         ~250 LOC  — interactive Q&A path (--initial-account prompt etc.)
#   scheduler_driver.py    ~250 LOC  — schedule library setup, _FakeScheduler, _get_process_tzname
#   main.py                <150 LOC  — argparse parse → dispatch → crash boundary
#
# _LAST_LOADED_STATE invariant (STATE.md Plan 03): single-singleton across the daemon. Lives in
# daily_loop.py — every consumer imports from there.
#
# Public CLI surface unchanged. ExecStart=python main.py works as before.
#
# Test-import-parity strategy: Option A — main.py re-exports every helper that test_main.py /
# test_scheduler.py reference, so test imports `from main import _handle_reset` etc. continue to work.
# Option B (update test imports) would create test churn; we keep Option A for locality.
#
# > Most eloquent: Option A — main.py is the single entry point + shim. Tests don't care
# > about internal reorg.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Inventory main.py — manifest</name>
  <read_first>
    - main.py (full — read in chunks of ~500 LOC)
    - tests/test_main.py
    - tests/test_scheduler.py
  </read_first>
  <action>
1. Read main.py in chunks. Classify every function/class into one of the four seams.
2. Capture test-side public API:
   ```bash
   grep -nE 'main\.[a-zA-Z_]|from main import' tests/test_main.py tests/test_scheduler.py
   ```
   Each name is a shim re-export.
3. Write manifest to `.planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/main-split-manifest.md` with:
   - line range → target seam
   - re-export list for main.py shim
   - cross-module edges (confirm acyclic — daily_loop and scheduler_driver may both reference cli_parser; that's fine)
4. Verify _LAST_LOADED_STATE invariant: it lives ONLY in daily_loop.py.
  </action>
  <verify>
    <automated>test -f .planning/phases/27-code-quality-correctness-sweep-apply-2026-05-07-code-review-/main-split-manifest.md</automated>
  </verify>
  <done>
    - Manifest written.
    - Test-import surface enumerated.
    - No circular imports.
    - _LAST_LOADED_STATE singleton confirmed.
  </done>
</task>

<task type="auto">
  <name>Task 2: Create new modules; move per manifest; main.py becomes thin entry + re-export shim</name>
  <read_first>
    - manifest from Task 1
    - main.py
  </read_first>
  <action>
1. Create cli_parser.py, daily_loop.py, interactive.py, scheduler_driver.py.
2. Move functions per manifest. Preserve docstrings, Phase-tag comments, decision references.
3. Wire intra-package imports.
4. Rewrite main.py as a thin entry + re-export shim:
   ```python
   '''Trading Signals — entry point. Phase 27 #3 split.

   Logic now lives in:
     - cli_parser.py        — argparse + flag validation
     - daily_loop.py        — run_daily_check, _LAST_LOADED_STATE singleton
     - interactive.py       — interactive Q&A path
     - scheduler_driver.py  — schedule library wiring

   This file is the entry point + re-export shim for test compatibility.
   '''
   import sys
   from cli_parser import _build_parser, _validate_flag_combo, _mode_label  # noqa: F401
   from daily_loop import (  # noqa: F401
     run_daily_check, _run_daily_check_caught, _handle_reset, _LAST_LOADED_STATE,
   )
   from interactive import interactive_q_and_a  # noqa: F401 — adjust to actual public name
   from scheduler_driver import _get_process_tzname, _FakeScheduler  # noqa: F401
   from system_params import STRATEGY_VERSION

   def main(argv: list[str] | None = None) -> int:
     parser = _build_parser()
     args = parser.parse_args(argv)
     if getattr(args, 'version', False):
       print(STRATEGY_VERSION); return 0
     _validate_flag_combo(args, parser)
     # dispatch logic — keep the existing main()-body branching (--reset / --test /
     # --force-email / --once / daemon). Each branch calls into one of the new modules.
     return _dispatch(args)

   if __name__ == '__main__':
     sys.exit(main())
   ```
5. The `_dispatch(args)` function lives in main.py (it's pure routing, ~30 LOC).
6. Run `pytest tests/test_main.py tests/test_scheduler.py -x` — MUST pass unchanged. Add re-exports if a test fails on missing name.
7. Run full `pytest -x`.
8. Sanity:
   ```
   python main.py --version       # prints version
   python main.py --help          # argparse help unchanged
   wc -l main.py cli_parser.py daily_loop.py interactive.py scheduler_driver.py
   ```
  </action>
  <verify>
    <automated>pytest tests/test_main.py tests/test_scheduler.py -x</automated>
  </verify>
  <done>
    - 4 new modules created.
    - main.py <150 LOC; each new module <500 LOC.
    - test_main.py + test_scheduler.py green without test changes.
    - Full suite green.
    - python main.py --version + --help work.
  </done>
</task>

<task type="auto">
  <name>Task 3: Parity test — CLI surface + re-exports</name>
  <read_first>
    - main.py (post-split)
  </read_first>
  <action>
1. **tests/test_main_split_seam.py (NEW):**
   ```python
   import subprocess, sys
   def test_main_py_is_thin():
     import pathlib
     assert pathlib.Path('main.py').read_text().count('\n') < 200, 'main.py exceeded thin shim budget'

   def test_cli_version_works():
     r = subprocess.run([sys.executable, 'main.py', '--version'], capture_output=True, text=True)
     assert r.returncode == 0
     assert r.stdout.strip().startswith('v')

   def test_cli_help_works():
     r = subprocess.run([sys.executable, 'main.py', '--help'], capture_output=True, text=True)
     assert r.returncode == 0
     assert '--once' in r.stdout
     assert '--version' in r.stdout

   def test_main_re_exports():
     import main
     for name in ['_build_parser', 'run_daily_check', '_handle_reset', '_LAST_LOADED_STATE',
                  '_FakeScheduler', '_get_process_tzname']:
       assert hasattr(main, name), f'{name} missing from main.py shim'

   def test_new_modules_under_500_loc():
     import pathlib
     for f in ['cli_parser.py', 'daily_loop.py', 'interactive.py', 'scheduler_driver.py']:
       loc = pathlib.Path(f).read_text().count('\n')
       assert loc < 500, f'{f} exceeded 500 LOC: {loc}'
   ```
  </action>
  <verify>
    <automated>pytest tests/test_main_split_seam.py -x -v</automated>
  </verify>
  <done>5 parity tests green.</done>
</task>

</tasks>

<threat_model>
N/A — pure code reorganisation. No security-relevant surface change.
</threat_model>

<verification>
```
pytest tests/test_main.py tests/test_scheduler.py tests/test_main_split_seam.py -x
wc -l main.py cli_parser.py daily_loop.py interactive.py scheduler_driver.py
python main.py --version
python main.py --help
pytest -x   # full suite
```
</verification>

<success_criteria>
- main.py <150 LOC; cli_parser/daily_loop/interactive/scheduler_driver each <500 LOC.
- Public CLI surface unchanged.
- tests/test_main.py + tests/test_scheduler.py pass unchanged.
- 5 new parity tests green.
- Full suite green.
</success_criteria>

<output>
Create `27-13-SUMMARY.md` with: manifest summary, line counts before/after, re-export list, parity test results.
</output>
