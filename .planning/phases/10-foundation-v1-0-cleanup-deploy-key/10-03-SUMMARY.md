---
plan: 10-03
phase: 10-foundation-v1-0-cleanup-deploy-key
requirements_addressed: [INFRA-02]
status: complete
completed: 2026-04-24
---

# Plan 10-03 Summary — INFRA-02 Droplet-side state.json Push

## Outcome

Added `main._push_state_to_git(state, now)` helper that commits + pushes `state.json` to `origin/main` via a deploy-key-authenticated git remote at the end of every successful weekday run. Never crashes the daily run; fails loud with structured warnings on the next cycle. Preserves hex-lite boundary (`state_manager.py` untouched by this change) and the Phase 8 W3 two-saves-per-run invariant.

## What was built

**Helper function** — `main.py:191-397` (~210 LOC):
- Local `import subprocess` inside the function body (C-2 pattern; mirrors `_send_email_never_crash`). Docstring documents REVIEW-LOW Option A rationale.
- **D-09** skip-if-unchanged: `git diff --quiet state.json` three-way exit code branch (rc=0 skip, rc=1 proceed, rc>=128 fail-loud).
- **D-10** inline identity flags: `-c user.email=droplet@trading-signals -c user.name='DO Droplet'` (does NOT mutate `.git/config`).
- **D-11** verbatim commit message from v1.0 Phase 7: `chore(state): daily signal update [skip ci]`.
- **T-10-03** explicit `state.json` positional arg on commit — prevents scope creep to other modified files.
- **D-13** no auto-rebase retry; fail-loud on push.
- **D-12** fail-loud via `state_manager.append_warning(source='state_pusher')` on every failure branch. **No third `save_state()`** — Phase 8 W3 invariant preserved; warning persists via next run's normal save cycle.
- **REVIEW-LOW** separate `try/except` blocks for commit vs push vs diff, so log verbs distinguish the failing subcommand: `[State] git commit failed` / `[State] git push failed` / `[State] git diff failed`.
- Timeout hygiene: `timeout=30` on diff and commit, `timeout=60` on push. Nested `try/except` around each `append_warning` call so append_warning failures never mask the original error.

**Wire-up** — `main.py:1287`:
- Call inserted at the end of `run_daily_check()` after `_render_dashboard_never_crash`, before the footer formatter.
- **D-15** structural guarantee: `--test` and weekend paths return from `run_daily_check` BEFORE reaching this line (early returns at `if args.test: return` and the weekday gate). Verified by `TestRunDailyCheckPushesState` tests.

**Test coverage** — `tests/test_main.py` (+396 lines, 2 new classes):
- `TestPushStateToGit` (6 tests) — subprocess-mocked unit coverage:
  - `test_skip_if_unchanged_logs_and_returns` (D-09)
  - `test_happy_path_commits_with_inline_identity_and_pushes` (D-08/D-10/D-11)
  - `test_push_failure_logs_error_and_appends_warning` (D-12 + REVIEW-LOW push verb)
  - `test_commit_failure_logs_error_and_appends_warning` (REVIEW-LOW commit verb, short-circuits before push)
  - `test_diff_error_appends_warning_without_pushing` (D-12 rc=128 edge)
  - `test_never_calls_save_state_on_push_failure` (Phase 8 W3 invariant)
- `TestRunDailyCheckPushesState` (4 tests) — integration coverage via direct `run_daily_check()` invocation:
  - `test_run_daily_check_invokes_push_after_save` (D-08 wiring, Monday freeze_time)
  - `test_run_daily_check_does_not_push_on_test_mode` (D-15, REVIEW-MEDIUM — NEW)
  - `test_run_daily_check_does_not_push_on_weekend` (D-15, REVIEW-MEDIUM — NEW, Saturday freeze_time)
  - `test_main_cli_dispatch_reaches_push_helper_smoke` (REVIEW-MEDIUM retained CLI smoke)

## Verification

- **Unit tests (new):** `pytest tests/test_main.py::TestPushStateToGit tests/test_main.py::TestRunDailyCheckPushesState -q` → 10 passed in 0.70s.
- **Full regression suite:** `pytest -x -q` → 681 passed in 93.35s (+10 from Wave 1's 671 baseline).
- **Hex-lite:** `state_manager.py` diff is empty — no subprocess/git imports added; the module remains I/O-narrow (disk only).
- **W3 invariant:** `test_never_calls_save_state_on_push_failure` spies on `state_manager.save_state` and asserts `save_calls == []` after a push-failure run through `_push_state_to_git`.
- **Ruff:** `ruff check main.py` → all checks passed. `ruff check tests/test_main.py` shows 12 style warnings, 11 pre-existing from prior phases and 1 in plan-copied boilerplate at line 2073 (UP027 unpacked list comp for unpacking — non-blocking style suggestion; not a regression).

## Commits

- `4e83048` — feat(10-03): add _push_state_to_git helper and wire into run_daily_check
- `4a306a0` — test(10-03): add TestPushStateToGit + TestRunDailyCheckPushesState (10 tests)
- (this file) — docs(10-03): INFRA-02 plan summary

## Acceptance criteria met (per 10-03-PLAN.md)

- `grep -q "def _push_state_to_git" main.py` ✓
- `grep -q "mirrors the .*_send_email_never_crash pattern" main.py` ✓ (docstring)
- `grep -q "REVIEW-LOW Option A" main.py` ✓
- `grep -q "git diff --quiet" main.py` ✓ (3 occurrences: helper, test)
- `grep -q "user.email=droplet@trading-signals" main.py` ✓
- `grep -q "user.name=DO Droplet" main.py` ✓
- `grep -q "chore(state): daily signal update \[skip ci\]" main.py` ✓
- `grep -q "source='state_pusher'" main.py` ✓ (9 occurrences across failure branches)
- `grep -q "\[State\] git commit failed" main.py` ✓
- `grep -q "\[State\] git push failed" main.py` ✓
- `grep -q "\[State\] git diff failed" main.py` ✓
- `grep -q "class TestPushStateToGit" tests/test_main.py` ✓
- `grep -q "class TestRunDailyCheckPushesState" tests/test_main.py` ✓
- `grep -q "test_run_daily_check_does_not_push_on_weekend" tests/test_main.py` ✓
- `grep -q "test_run_daily_check_does_not_push_on_test_mode" tests/test_main.py` ✓
- `grep -q "test_main_cli_dispatch_reaches_push_helper_smoke" tests/test_main.py` ✓
- `grep -c "save_state(state)" main.py` ≤ baseline ✓ (5 occurrences — unchanged: 3 real calls + 2 docstring references)

## Deviations

**Execution path:** The spawned executor agent hit sandbox restrictions and could not run `git commit`, `pytest`, or `ruff`. Task 1 was staged but uncommitted; Task 2 was not started. The orchestrator took over inline, applied the staged Task 1 patch on the main branch, committed it, authored Task 2 test code from the plan's verbatim spec (plan 10-03-PLAN.md lines 560-971), ran the test suite (all green), and committed. Worktree branch `worktree-agent-aa15fcee` was not merged back (uncommitted Task 1 only); the worktree will be cleaned up by the runtime and the branch remains unreachable.

**Substantive deviations:** None. All D-decisions, REVIEW fixes, and acceptance criteria honored. Helper body and test bodies are verbatim from the plan.

## Files modified

- `main.py` — +216 lines (_push_state_to_git helper at 191-397; wire-up at 1287)
- `tests/test_main.py` — +396 lines (TestPushStateToGit + TestRunDailyCheckPushesState)

## Next

Plan 10-04 (INFRA-03 GHA retirement + SETUP-DEPLOY-KEY.md + D-19 prose). Depends on this plan for the `_push_state_to_git` helper name reference in SETUP-DEPLOY-KEY.md.
