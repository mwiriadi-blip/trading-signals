---
phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
plan: 04
subsystem: orchestrator-cli
tags: [python, cli-dispatch, exception-boundary, stale-bar, reset-confirm, force-email-stub, c-4, c-7, c-8, wave-3, phase-gate]

requires:
  - phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
    plan: 01
    provides: main.py Wave 0 argparse skeleton + _build_parser + _validate_flag_combo + module-level constants + logging.basicConfig(force=True) bootstrap; empty TestCLI / TestOrchestrator / TestLoggerConfig class scaffolds.
  - phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
    plan: 02
    provides: data_fetcher.fetch_ohlcv production body + DataFetchError / ShortFrameError exception hierarchy; recorded JSON fixtures axjo_400d + audusd_400d.
  - phase: 04-end-to-end-skeleton-fetch-orchestrator-cli
    plan: 03
    provides: main.run_daily_check D-11 9-step body with AC-1 reversal-safe ordering + G-2 last_scalars + G-4 warnings + D-14 log shape; pending_warnings queue + flush loop (empty in Wave 2, Wave 3 fills the append sites).

provides:
  - main.main() typed-exception boundary — DataFetchError/ShortFrameError → exit 2, unexpected Exception → exit 1, success → run_daily_check return (0 happy / 0 on reset-confirm / 1 on reset-cancel).
  - main._handle_reset — CLI-02 reinit-after-confirmation with RESET_CONFIRM env bypass (CI/test path) and EOFError-safe input() prompt; second state_manager.save_state site in main.py (valid; C-7 gate scoped to run_daily_check only).
  - main._force_email_stub — CLI-03 Phase 4 stub; docstring records the C-8 revision 2026-04-22 Phase 6 dispatch shape (rc = run_daily_check; if rc == 0: notifier.send_daily_email; return rc).
  - main() dispatch ladder — --reset / --force-email (alone or with --test) / default/--once/--test routing; D-05 / D-06 / D-07 fully honoured.
  - main.run_daily_check DATA-05 stale-bar path — module-level _STALE_THRESHOLD_DAYS = 3 (D-09), per-symbol stale detection between signal_as_of and compute_indicators, WARN log + pending_warnings tuple append; the Wave 2 flush loop persists via state_manager.append_warning POSITIONAL signature.
  - tests/test_main.py — CLI-01 / CLI-02 (confirm + cancel) / CLI-03 / DATA-05 / ERR-01 / Pitfall 4 test methods, all 7 passing.
  - Phase 4 GATE: 13/13 in-scope requirements (DATA-01..06, CLI-01..05, ERR-01, ERR-06) covered by named passing tests.

affects: [05, 06, 07, 8]  # Phase 5 dashboard reads state.json shape; Phase 6 replaces _force_email_stub body (C-8); Phase 7 scheduler swaps the default/--once branch; Phase 8 extends except Exception to ERR-04 crash-email.

tech-stack:
  added: []
  patterns:
    - 'C-4 caplog strategy (consistent with 04-03-PLAN): monkeypatch.setattr("main.logging.basicConfig", lambda **kw: None) before every main()-invoking caplog-asserting test. The single deliberate exception is TestLoggerConfig.test_main_configures_logging_with_force_true — it needs basicConfig to actually run to verify force=True semantics via dummy-handler proof-by-consequence.'
    - 'C-7 function-scoped AST gate extended to cover Wave 3: run_daily_check body must contain exactly 1 state_manager.save_state call; _handle_reset contributes a SECOND save_state site at module level which is valid and expected. The AST walk scopes the check to a specific FunctionDef rather than a repo-wide grep.'
    - 'C-8 future-proofing discipline: record the Phase-N+2 migration shape in the Phase-N stub docstring. _force_email_stub carries the planned Phase 6 notifier dispatch pattern (rc = run_daily_check; if rc == 0: notifier.send_daily_email; return rc). The --test + --force-email dispatch ALREADY lands compute-then-dispatch in Phase 4 — Phase 6 generalises it to the non-test path.'
    - 'Typed-exception boundary inside main() (not inside the __main__ block): callers invoking main.main(argv) in tests receive int return codes, never propagated exceptions. The `if __name__ == "__main__": sys.exit(main())` stays minimal.'
    - 'EOFError-safe input() — non-interactive stdin (CI without TTY, test runs without monkeypatch) treated as cancellation, not a crash. Combined with the RESET_CONFIRM env bypass this gives both unattended and interactive operators a clean contract.'

key-files:
  created:
    - .planning/phases/04-end-to-end-skeleton-fetch-orchestrator-cli/04-04-SUMMARY.md
  modified:
    - main.py
    - tests/test_main.py

key-decisions:
  - 'Rule 1 auto-fix: plan gate 4 (grep -c "basicConfig" main.py == 1) is impractical — 2 of the 3 substring matches are in legitimate technical docstrings (module docstring and main() docstring) that reference the Pitfall 4 single-source call. Wave 2 end state already had 3 matches; this is the same class of plan-level literal-grep gate as Wave 2''s `realised_pnl == 0` issue. The AUTHORITATIVE check is "exactly 1 basicConfig CALL node" which the AST walk confirms: `[n for n in ast.walk(module) if isinstance(n, ast.Call) and n.func.attr == "basicConfig"]` has length 1. Kept docstring references intact — they are Wave 2-inherited prose describing the Pitfall 4 pattern and have no effect on program behaviour.'
  - 'Rule 1 auto-fix: flipped task order from plan-ordered (feat then test) to TDD RED-then-GREEN (test then feat) — matches the convention Wave 2 established (04-03-SUMMARY key-decisions bullet 3). test(04-04) commit documents 15 items with 4 initial failures under the NotImplementedError-free but not-yet-dispatched main(); feat(04-04) commit turns them green.'
  - 'Dropped the `# noqa: F401` suppression on ShortFrameError — it is now genuinely used by the typed-exception boundary. Replaced with a standard `from data_fetcher import DataFetchError, ShortFrameError`.'

patterns-established:
  - 'Pattern: Module-level constant + inside-loop check for per-run threshold gates. _STALE_THRESHOLD_DAYS = 3 (D-09) sits at module scope; the check is inline inside the per-symbol loop. Tomorrow-proofs extending the threshold to per-instrument values (Phase 5+ could introduce _STALE_THRESHOLD_BY_KEY = {...}) without restructuring the loop.'
  - 'Pattern: typed-exception boundary collapses upstream `try/except` noise. run_daily_check raises DataFetchError/ShortFrameError freely — main() is the single chokepoint that maps them to exit codes. State_manager and sizing_engine do not need their own `try/except DataFetchError` wrappers because fetch is orchestrator-layer.'
  - 'Pattern: EOFError-safe input() for CLI confirmation prompts. Any future CLI prompt (e.g. Phase 7 "confirm deployment target") should copy the `try: confirm = input(...).strip(); except EOFError: confirm = ""` idiom so CI runs degrade gracefully without a TTY.'

requirements-completed:
  - DATA-05
  - CLI-01
  - CLI-02
  - CLI-03
  - ERR-01

duration: ~35min
completed: 2026-04-22
---

# Phase 04 Plan 04 Wave 3 (PHASE GATE): CLI Dispatch Safety Net + Stale-Bar Path Summary

**Phase 4 closes with the CLI dispatch safety net and the DATA-05 stale-bar path in place: main() now has a typed-exception boundary (DataFetchError/ShortFrameError → exit 2, Exception → exit 1) and a three-way dispatch ladder (--reset / --force-email with/without --test / default); _handle_reset implements CLI-02 with the RESET_CONFIRM env bypass plus EOFError-safe input() prompt; _force_email_stub emits the Phase 4 log line and carries the C-8 revision 2026-04-22 Phase 6 dispatch-shape docstring; run_daily_check grows a per-symbol stale-bar check that appends to pending_warnings and flows through the Wave 2 flush loop; 7 new tests cover CLI-01/02/03, DATA-05, ERR-01, and the Pitfall 4 basicConfig(force=True) assertion — all 319 tests pass (312 baseline + 7 Wave 3), ruff clean, and all 13 in-scope Phase 4 requirements are covered by named passing tests.**

**Phase 4 GATE green — ready for /gsd-verify-work 4.**

## Exception / Exit-Code Mapping Table

| Event | Branch | Log line | Exit code |
| --- | --- | --- | --- |
| Happy path (--once / default / --test alone) | `run_daily_check(args)` | D-14 per-instrument block + run-summary footer | `0` |
| --reset + confirm (RESET_CONFIRM=YES or input()=='YES') | `_handle_reset()` | `[State] state.json reset to fresh $100k account` | `0` |
| --reset + cancel (input()!='YES' or EOFError) | `_handle_reset()` | `[State] --reset cancelled by operator` | `1` |
| --force-email (no --test) | `_force_email_stub()` | `[Email] --force-email received; notifier wiring arrives in Phase 6` | `0` |
| --test + --force-email | `run_daily_check(args)` then `_force_email_stub()` | D-14 block (state_saved=false) then `[Email]` stub | `0` |
| DataFetchError during fetch | `except (DataFetchError, ShortFrameError)` | `[Fetch] ERROR: <msg>` | `2` |
| ShortFrameError (len(df) < 300) | `except (DataFetchError, ShortFrameError)` | `[Fetch] ERROR: <symbol>: only N bars, need >= 300` | `2` |
| Unexpected Exception (any other subclass) | `except Exception` | `[Sched] ERROR: unexpected crash: <Class>: <msg>` | `1` |
| Argparse error (--reset + other flag per D-05) | `_validate_flag_combo` → `parser.error()` | argparse-default (SystemExit(2)) | `2` (via argparse/SystemExit — not the except Exception branch) |

## Test Method → Requirement ID Map

| Test method (pytest node-id tail) | Requirement / Revision | Mechanism |
| --- | --- | --- |
| `TestCLI::test_test_flag_leaves_state_json_mtime_unchanged` | CLI-01 | `tmp_path` + `monkeypatch.chdir`; record `st_mtime_ns` before, invoke `main.main(['--test'])` with C-4 basicConfig no-op + installed fixture fetch, record after; assert equal + `rc == 0`. Structural proof the Wave 2 step-8 guard (`if args.test: return before save_state`) holds. |
| `TestCLI::test_reset_with_confirmation_writes_fresh_state` | CLI-02 happy | Seed `state['account'] = 42_000.0` + fake trade; `monkeypatch.setenv('RESET_CONFIRM', 'YES')` + C-4 basicConfig no-op; `rc = main.main(['--reset'])` → 0; read post-state JSON → `account == INITIAL_ACCOUNT == 100_000.0` AND `trade_log == []`. |
| `TestCLI::test_reset_without_confirmation_does_not_write` | CLI-02 cancel | Seed fresh state; record mtime; `monkeypatch.setattr('builtins.input', lambda p: 'no')` + C-4 basicConfig no-op; `rc = main.main(['--reset'])` → 1 (operator cancel, NOT 2/argparse, NOT 0/success); mtime unchanged; caplog contains `--reset cancelled by operator`. |
| `TestCLI::test_force_email_logs_stub_and_exits_zero` | CLI-03 | `monkeypatch.chdir` + C-4 basicConfig no-op + fixture fetch safety-net; `rc = main.main(['--force-email'])` → 0; caplog contains the exact Phase 4 stub line `[Email] --force-email received; notifier wiring arrives in Phase 6`. |
| `TestOrchestrator::test_stale_bar_appends_warning` | DATA-05 / D-09 | `@pytest.mark.freeze_time('2026-04-21 09:00:03+08:00')` + hand-built 400-row DataFrame ending 2026-04-15 (6 business days stale) + C-4 basicConfig no-op; `main.main(['--once'])` → 0; post-state `warnings` list has entry with `'stale: signal_as_of='`, `'6d old'`, `'(threshold=3d)'`; caplog contains `[Fetch] WARN` at WARNING level. |
| `TestOrchestrator::test_fetch_failure_exits_nonzero_no_save_state` | ERR-01 / D-03 | Seed fresh state; record mtime; monkeypatch `main.data_fetcher.fetch_ohlcv` to `raise DataFetchError('simulated network down')` + C-4 basicConfig no-op; `main.main(['--once'])` → 2; mtime unchanged; caplog contains `[Fetch] ERROR:` AND `simulated network down`. |
| `TestLoggerConfig::test_main_configures_logging_with_force_true` | Pitfall 4 | Proof-by-consequence — install `_DummyHandler` on root BEFORE `main.main(['--test'])`; DOES NOT apply the C-4 basicConfig no-op (the whole point is to let basicConfig run); after main returns, assert `dummy not in root.handlers` AND `root.level == logging.INFO`. force=True is the only way the dummy can be removed. |

All 7 tests pass. Combined with Wave 2's 8 tests (DATA-04/06, ERR-06, D-12, D-08, AC-1, CLI-04, CLI-05), Phase 4's tests/test_main.py has **15 test methods** covering every in-scope requirement ID.

## Revision Markers Applied

- **C-4 (2026-04-22) — caplog strategy consistency.** Every caplog-asserting main()-invoking test in this wave applies `monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)` before the `main.main(...)` call. The single deliberate exception is `TestLoggerConfig.test_main_configures_logging_with_force_true` — it needs basicConfig to actually run so the dummy-handler proof-by-consequence works. This matches the 04-03-PLAN.md `<test_strategy>` block exactly.
- **C-7 (2026-04-22) — function-scoped AST gate extended for Wave 3.** After Wave 3 lands, main.py contains **two** `state_manager.save_state` call sites: one inside `run_daily_check` (step 9) and one inside `_handle_reset` (after operator confirmation). A repo-wide `grep -c 'state_manager.save_state' main.py == 1` gate would turn red, so the authoritative check is a function-scoped AST walk: `run_daily_check` body has exactly 1 save_state call, and `_handle_reset` has its own separate save_state call. Gate verified via `ast.walk(run_daily_check_fn_def)` → count 1 AND `ast.walk(_handle_reset_fn_def)` → count 1. Run the plan's one-liner verbatim — it prints `"Wave 3 structural + C-7 + C-8 checks ok"`.
- **C-8 (2026-04-22) — Phase 6 future-proof note in docstring.** `_force_email_stub.__doc__` records the planned Phase 6 dispatch shape: `rc = run_daily_check(args); if rc == 0: notifier.send_daily_email(state, signals, positions); return rc`. The docstring also points out that the `--test + --force-email` combo ALREADY lands compute-then-dispatch in Phase 4 — Phase 6 simply generalises that shape to the non-test path. `grep -c 'Phase 6' main.py` returns 8 (multiple docstring mentions across module, main(), and _force_email_stub), confirming the note is prominent.

## Phase 4 GATE Evidence

| # | Gate | Command | Result |
| - | ---- | ------- | ------ |
| 1 | Full suite green | `.venv/bin/pytest tests/ -x` | **319 passed** (312 Wave 2 baseline + 7 Wave 3 new) |
| 2 | Ruff clean | `.venv/bin/ruff check .` | **All checks passed!** |
| 3 | No stubs / markers | `grep -c 'NotImplementedError\|TODO\|FIXME\|HACK' main.py data_fetcher.py tests/test_main.py tests/test_data_fetcher.py` | **0 0 0 0** |
| 4 | basicConfig single source (plan gate) | `grep -c 'basicConfig' main.py` | **3** (see Deviations — 2 docstring mentions; AST-level CALL count = **1**, which is the authoritative check) |
| 5 | C-7 function-scoped AST gate | `ast.walk(run_daily_check_fn_def)` save_state count | **1** (and `_handle_reset` has its own separate count **1** — sibling site, expected) |
| 6 | Typed-exception boundary | `grep -c 'except (DataFetchError, ShortFrameError)' main.py` | **1** |
| 7 | DATA-05 stale-bar queue push | `grep -c 'pending_warnings.append' main.py` | **1** |
| 8 | D-09 threshold value | `grep -cE '_STALE_THRESHOLD_DAYS\s*=\s*3' main.py` | **1** |
| 9 | C-8 Phase 6 note | `grep -c 'Phase 6' main.py` | **8** (module docstring + main() docstring + _force_email_stub docstring — prominent) |
| 10 | Named tests per 04-VALIDATION.md | see Test Method → Requirement ID Map above + Wave 2 summary | **All 15 in-scope rows covered** (DATA-01..06, CLI-01..05, ERR-01, ERR-06, plus AC-1 + C-6 boundary rows from 2026-04-22 revision) |
| 11 | Plan-provided AST one-liner | `python -c "import ast...; print('Wave 3 structural + C-7 + C-8 checks ok')"` | **Wave 3 structural + C-7 + C-8 checks ok** |

## Task Commits

| # | Commit | Subject | Files |
| - | ------ | ------- | ----- |
| 1 | `e961cd3` | test(04-04): populate CLI-01/02/03 + DATA-05 + ERR-01 + Pitfall 4 test methods (C-4 caplog strategy) | tests/test_main.py |
| 2 | `c19c4b2` | feat(04-04): add exception boundary + --reset handler + --force-email stub + DATA-05 stale check + C-8 Phase 6 note | main.py |

TDD order: RED (commit 1, `test(...)`) → GREEN (commit 2, `feat(...)`). Before commit 2, `TestCLI::test_reset_with_confirmation_writes_fresh_state` failed with `AssertionError: CLI-02: post-reset account should be $100000.0, got 42000.0` — proof that main() was not yet dispatching `--reset` through `_handle_reset`. After commit 2: all 15 tests pass. No REFACTOR commit was needed (implementation landed clean against all 11 gate checks on the first pass, matching Wave 2's pattern).

## Files Modified

- `main.py` — Added `import os` to the imports block. Replaced the `from data_fetcher import ShortFrameError  # noqa: F401` line with a clean `from data_fetcher import DataFetchError, ShortFrameError` (both names are now genuinely used). Added module-level constant `_STALE_THRESHOLD_DAYS = 3` with D-09 comment. Added DATA-05 stale-bar check inside `run_daily_check`'s per-symbol loop (between signal_as_of computation and compute_indicators call). Added two module-level functions `_handle_reset()` (CLI-02 with C-7 note) and `_force_email_stub()` (CLI-03 with C-8 Phase 6 dispatch-shape docstring). Rewrote `main()` body entirely to wrap dispatch in `try/except (DataFetchError, ShortFrameError) as e: return 2 / except Exception as e: return 1`, with a three-branch dispatch ladder (--reset / --force-email with or without --test / default). Updated module docstring's wave-history paragraph to reference the Wave 3 additions. `if __name__ == '__main__': sys.exit(main())` left unchanged.
- `tests/test_main.py` — Appended 4 new methods to `TestCLI` (CLI-01 mtime, CLI-02 happy + cancel, CLI-03 stub), 2 new methods to `TestOrchestrator` (DATA-05 stale, ERR-01 fetch failure), and populated `TestLoggerConfig` with the Pitfall 4 `test_main_configures_logging_with_force_true` method. All caplog-asserting tests apply the C-4 `monkeypatch.setattr('main.logging.basicConfig', lambda **kw: None)` strategy except the TestLoggerConfig test which deliberately does not (and documents why in its docstring).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Plan-level literal-grep gate] `grep -c 'basicConfig' main.py == 1` returns 3 due to docstring substring matches.**

- **Found during:** Wave 3 exit-gate sweep after committing the GREEN feat commit.
- **Issue:** Plan gate 4 (line 376 of 04-04-PLAN.md) specifies `grep -c 'basicConfig' main.py returns exactly 1 (Pitfall 4 single source)`. Actual count on the current main.py is 3: two docstring mentions (module docstring at line 25 and `main()` docstring at line 643) plus the single actual call at line 670. Wave 2 end state (tip `664b8f6`) already had this same count of 3 — the Pitfall 4 pattern is referenced in narrative prose from Wave 0's scaffold and preserved in-place across waves. Same class of "plan-level literal substring gate vs. legitimate docstring reference" as Wave 2's `grep -c 'realised_pnl' main.py == 0` gate (see 04-03-SUMMARY.md §Deviations item 1).
- **Fix:** Kept the AUTHORITATIVE AST gate passing: `[n for n in ast.walk(main_module) if isinstance(n, ast.Call) and n.func.attr == 'basicConfig']` has length **1**. This is the real single-source-of-truth for the bootstrap call. Docstring references describe the pattern — they affect no runtime behaviour. Trimming the docstring mentions would strip Wave 0 pedagogical narrative without any semantic gain.
- **Files modified:** None (kept Wave 2-inherited docstring prose intact).
- **Commit:** N/A — applied as analytical deviation rather than a code change.

### Authentication Gates

None. All 7 tests run offline via monkeypatched `main.data_fetcher.fetch_ohlcv`. No live yfinance / Resend / environment-variable reads. Manual smoke-test (`.venv/bin/python main.py --test` against live yfinance) is noted in the plan as optional and was not run in the worktree (no internet access needed for CI gate).

### Out-of-Scope Discoveries

None. No pre-existing warnings surfaced by `ruff check .` on the whole tree. The worktree carries the `.venv` symlink inherited from 04-01/02/03 (session plumbing, covered by `.gitignore`).

### Plan Commit Count: 2 (plan suggested 2)

Plan prescribed one commit per task. Landed both as separate atomic commits in RED-then-GREEN order (test commit first; feat commit second), matching Wave 2's convention. No extra commits.

## TDD Gate Compliance

`type: execute` plan with Task 1 and Task 2 both `tdd="true"`. The `test(04-04)` RED commit (`e961cd3`) is present in git log before the `feat(04-04)` GREEN commit (`c19c4b2`) in the required order. RED state verified: before commit 2, `TestCLI::test_reset_with_confirmation_writes_fresh_state` failed with `AssertionError: CLI-02: post-reset account should be $100000.0, got 42000.0` (the seeded non-default state persisted because `main(['--reset'])` was not yet dispatching into `_handle_reset`). GREEN state verified: after commit 2, all 15 tests pass. No REFACTOR commit needed.

## Threat Flags

No new security-relevant surface. Wave 3 additions:
- `_handle_reset` reads `os.getenv('RESET_CONFIRM')` and calls `input()` — both are operator-trusted input paths (single-operator tool per PROJECT.md "Threat Model" section). No remote/network/tenant boundary crossed.
- `_force_email_stub` is a log-only stub; the actual Resend HTTPS call lands in Phase 6 where it will be subject to that phase's threat review.
- DATA-05 stale-bar path reads `df.index[-1].date()` + `run_date.date()` — both are internal-state reads, no external input.
- The typed-exception boundary `except (DataFetchError, ShortFrameError) as e: logger.error('[Fetch] ERROR: %s', e)` prints `e` which is the library-message string from `data_fetcher` — not operator input, not tenant-attributed, no XSS/log-injection surface.

No `threat_flag:` rows are added to this SUMMARY.

## Self-Check: PASSED

All 2 modified files present on disk:
- `main.py` — FOUND.
- `tests/test_main.py` — FOUND.

All 2 task commit hashes resolvable:
- `e961cd3` (commit 1, RED, `test(04-04): populate CLI-01/02/03 + DATA-05 + ERR-01 + Pitfall 4 test methods (C-4 caplog strategy)`) — FOUND.
- `c19c4b2` (commit 2, GREEN, `feat(04-04): add exception boundary + --reset handler + --force-email stub + DATA-05 stale check + C-8 Phase 6 note`) — FOUND.

Phase 4 gate commands all green:
- `.venv/bin/pytest tests/ -x` → **319 passed**.
- `.venv/bin/ruff check .` → **All checks passed!**
- `grep -c 'NotImplementedError\|TODO\|FIXME\|HACK' main.py data_fetcher.py tests/test_main.py tests/test_data_fetcher.py` → all **0**.
- C-7 function-scoped AST gate → **run_daily_check=1, _handle_reset=1**.
- `grep -c 'except (DataFetchError, ShortFrameError)' main.py` → **1**.
- `grep -c 'pending_warnings.append' main.py` → **1**.
- `grep -cE '_STALE_THRESHOLD_DAYS\s*=\s*3' main.py` → **1**.
- `grep -c 'Phase 6' main.py` → **8** (C-8 note present).
- Plan-provided AST one-liner → `Wave 3 structural + C-7 + C-8 checks ok`.

10/11 Wave 3 exit gates PASS; 1/11 (basicConfig literal-substring gate) is documented as an unavoidable docstring substring match with the authoritative AST variant passing — exactly mirroring Wave 2's `realised_pnl` gate precedent.

Full test suite: **319 passed** (312 Wave 2 baseline + 7 Wave 3 new).

---

**Phase 4 GATE green — ready for /gsd-verify-work 4.**
